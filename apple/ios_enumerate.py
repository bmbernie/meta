#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: bmbernie@gmail.com
# Created: 2026-10-15

import sys, json, re, shutil, subprocess, argparse
from datetime import datetime

PMD3 = shutil.which("pymobiledevice3") or "/Users/b/.local/bin/pymobiledevice3"
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
BANNER = "=" * 75

def run_pmd3(*args, show_err=False):
    """Run pymobiledevice3 CLI and parse JSON output cleanly."""
    for cmd in ([PMD3] + list(args) + ["--no-color"], [PMD3, "--no-color"] + list(args), [PMD3] + list(args)):
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        out = ANSI_RE.sub('', res.stdout).strip()
        if res.returncode == 0 and out:
            try:
                return json.loads(out)
            except Exception:
                return out
    if show_err:
        res = subprocess.run([PMD3] + list(args), capture_output=True, text=True, timeout=25)
        print(f"  [!] Command failed: {' '.join([PMD3] + list(args))}")
        print(f"      STDERR: {ANSI_RE.sub('', res.stderr).strip()}")
    return None

LOCKDOWN_DOMAINS = [
    "com.apple.disk_usage",
    "com.apple.disk_usage.factory",
    "com.apple.mobile.battery",
    "com.apple.iqagent",
    "com.apple.purplebuddy",
    "com.apple.PurpleBuddy",
    "com.apple.mobile.chaperone",
    "com.apple.mobile.third_party_termination",
    "com.apple.mobile.lockdownd",
    "com.apple.mobile.lockdown_cache",
    "com.apple.xcode.developerdomain",
    "com.apple.international",
    "com.apple.mobile.data_sync",
    "com.apple.mobile.tethered_sync",
    "com.apple.mobile.mobile_application_usage",
    "com.apple.mobile.backup",
    "com.apple.mobile.nikita",
    "com.apple.mobile.restriction",
    "com.apple.mobile.user_preferences",
    "com.apple.mobile.sync_data_class",
    "com.apple.mobile.software_behavior",
    "com.apple.mobile.internal",
    "com.apple.mobile.wireless_lockdown",
    "com.apple.fairplay",
    "com.apple.iTunes",
    "com.apple.mobile.iTunes.store",
    "com.apple.fmip",
]

def format_bytes(b):
    if not isinstance(b, (int, float)):
        return "N/A"
    return f"{b / (1024**3):.2f} GB ({b:,} bytes)"

def format_val(v):
    """Format complex nested dicts/lists cleanly for terminal display."""
    if isinstance(v, (dict, list)):
        s = json.dumps(v)
        return s if len(s) <= 100 else s[:97] + "..."
    return str(v)

def print_section_header(title):
    print("\n" + BANNER)
    print(title)
    print(BANNER)

def main():
    parser = argparse.ArgumentParser(
        description="Enumerate iPhone hardware, lockdown info, sub-domains, and diagnostics.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s", "--summary",
        action="store_true",
        help="Print executive summary and domain list without dumping every key-value pair."
    )
    args = parser.parse_args()

    print(f"Using CLI binary: {PMD3}")
    print("  [1/4] Enumerating usbmux list (USB)...")
    # Pass --no-pair so usbmux list doesn't automatically trigger a Trust popup on the phone!
    usbmux_list = (
        run_pmd3("usbmux", "list", "--usb", "--no-pair")
        or run_pmd3("usbmux", "list", "--usb")
        or run_pmd3("usbmux", "list", show_err=True)
    )

    udid = None
    if isinstance(usbmux_list, list):
        for dev in usbmux_list:
            if isinstance(dev, dict) and dev.get("UniqueDeviceID"):
                udid = dev.get("UniqueDeviceID")
                if dev.get("ConnectionType") == "USB":
                    break

    target_flags = ["--udid", udid] if udid else []
    if udid:
        print(f"        Target Device UDID: {udid}")

    print("  [2/4] Fetching full 'lockdown info'...")
    is_trusted_session = True
    lockdown_info = run_pmd3("lockdown", "info", *target_flags)

    if not isinstance(lockdown_info, dict):
        is_trusted_session = False
        if isinstance(usbmux_list, list) and usbmux_list and isinstance(usbmux_list[0], dict):
            print("  [!] Device is UNTRUSTED / UNPAIRED. Falling back to public pre-pairing lockdown keys...")
            lockdown_info = usbmux_list[0]
        else:
            print("Error: Could not read lockdown info.")
            sys.exit(1)

    if not udid:
        udid = lockdown_info.get("UniqueDeviceID", "unknown_udid")

    full_report = {
        "timestamp": datetime.now().isoformat(),
        "paired_session": is_trusted_session,
        "usbmux": usbmux_list,
        "lockdown_info": lockdown_info,
        "domains": {},
        "diagnostics": {}
    }

    if is_trusted_session:
        print("  [3/4] Probing Specialized Lockdownd Domains...")
        for domain in LOCKDOWN_DOMAINS:
            val = run_pmd3("lockdown", "get", domain, *target_flags)
            if val is None:
                val = run_pmd3("lockdown", "get", "-d", domain, *target_flags)
            if val:
                full_report["domains"][domain] = val

        print("  [4/4] Querying Hardware Diagnostics & SmartBattery IORegistry...")
        batt_diag = run_pmd3("diagnostics", "battery", "single", *target_flags)
        if isinstance(batt_diag, dict):
            full_report["diagnostics"]["battery"] = batt_diag

        ioreg_batt = run_pmd3("diagnostics", "ioregistry", "--entry", "AppleSmartBattery", *target_flags)
        if ioreg_batt:
            full_report["diagnostics"]["AppleSmartBattery"] = ioreg_batt
    else:
        print("  [3/4] Skipping Sub-Domains (Requires Trusted Pairing Session)...")
        print("  [4/4] Skipping Hardware Diagnostics (Requires Trusted Pairing Session)...")

    # Save JSON file named with the device's actual UDID (and _untrusted if unpaired)
    safe_udid = re.sub(r'[^A-Za-z0-9_-]', '_', str(udid))
    suffix = "info" if is_trusted_session else "untrusted_info"
    out_file = f"/tmp/iphone_{safe_udid}_{suffix}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, sort_keys=True)

    r = lockdown_info
    disk = full_report["domains"].get("com.apple.disk_usage", {})
    if not isinstance(disk, dict): disk = {}
    disk_factory = full_report["domains"].get("com.apple.disk_usage.factory", {})
    if not isinstance(disk_factory, dict): disk_factory = {}
    batt_dom = full_report["domains"].get("com.apple.mobile.battery", {})
    if not isinstance(batt_dom, dict): batt_dom = {}
    intl = full_report["domains"].get("com.apple.international", {})
    if not isinstance(intl, dict): intl = {}
    b_diag = full_report["diagnostics"].get("battery", {})
    if not isinstance(b_diag, dict): b_diag = {}

    model_num = r.get("ModelNumber", "")
    region = r.get("RegionInfo", "")
    reg_model = r.get("RegulatoryModelNumber") or "N/A"
    ecid = r.get("UniqueChipID", 0)
    chip_id = r.get("ChipID", 0)
    board_id = r.get("BoardId", 0)

    # =========================================================================
    # SECTION 1: SHARED IN BOTH DEFAULT AND SUMMARY (-s) VIEWS
    # =========================================================================
    print_section_header("SECTION 1: EXECUTIVE HARDWARE & SYSTEM SUMMARY")

    print("\n[IDENTITY & RETAIL HARDWARE]")
    print(f"  Device Name            : {r.get('DeviceName')}")
    print(f"  Marketing / Class      : {r.get('DeviceClass')} ({r.get('ProductType')})")
    print(f"  Hardware Board Model   : {r.get('HardwareModel')} (Platform: {r.get('HardwarePlatform')})")
    print(f"  Retail Part Number     : {(model_num + region) if (model_num or region) else 'N/A (Locked/Untrusted)'}")
    print(f"  Regulatory Model (A-#) : {reg_model}")
    print(f"  Serial Number          : {r.get('SerialNumber', 'N/A (Untrusted)')}")
    print(f"  UDID                   : {r.get('UniqueDeviceID')}")
    print(f"  ECID (Unique Chip ID)  : {ecid} (Hex: {hex(ecid).upper() if isinstance(ecid, int) else ecid})")
    print(f"  Chip ID / Board ID     : {hex(chip_id) if isinstance(chip_id, int) else chip_id} / {hex(board_id) if isinstance(board_id, int) else board_id}")
    print(f"  CPU Architecture       : {r.get('CPUArchitecture')}")
    print(f"  Device Enclosure Color : {r.get('DeviceEnclosureColor')} (DeviceColor: {r.get('DeviceColor')})")

    print("\n[OPERATING SYSTEM & FIRMWARE]")
    print(f"  iOS Version            : {r.get('ProductVersion')} (Build {r.get('BuildVersion')})")
    print(f"  Baseband (Modem) Ver   : {r.get('BasebandVersion', 'N/A')}")
    print(f"  Bootloader / Firmware  : {r.get('FirmwareVersion', 'N/A')}")
    print(f"  Activation State       : {r.get('ActivationState', 'N/A')}")
    print(f"  Password Protected     : {r.get('PasswordProtected')}")
    print(f"  Trusted Host Attached  : {r.get('TrustedHostAttached')}")
    print(f"  TimeZone / Locale      : {r.get('TimeZone', 'N/A')} / {intl.get('Locale', 'N/A')}")

    print("\n[NETWORK & CELLULAR RADIOS]")
    print(f"  Wi-Fi MAC Address      : {r.get('WiFiAddress', 'N/A')}")
    print(f"  Bluetooth MAC Address  : {r.get('BluetoothAddress', 'N/A')}")
    print(f"  Ethernet MAC Address   : {r.get('EthernetAddress', 'N/A')}")
    print(f"  Phone Number           : {r.get('PhoneNumber', 'N/A')}")
    print(f"  IMEI 1                 : {r.get('InternationalMobileEquipmentIdentity', 'N/A')}")
    print(f"  IMEI 2 (eSIM)          : {r.get('InternationalMobileEquipmentIdentity2', 'N/A')}")
    print(f"  ICCID                  : {r.get('IntegratedCircuitCardIdentity', 'N/A')}")

    print("\n[STORAGE & DISK USAGE (com.apple.disk_usage)]")
    print(f"  Total Disk Capacity    : {format_bytes(disk.get('TotalDiskCapacity'))}")
    print(f"  Total Data Capacity    : {format_bytes(disk.get('TotalDataCapacity'))}")
    print(f"  Total Data Available   : {format_bytes(disk.get('TotalDataAvailable'))}")
    print(f"  Total System Capacity  : {format_bytes(disk.get('TotalSystemCapacity'))}")
    photo_bytes = disk.get('PhotoUsage') if disk.get('PhotoUsage') is not None else disk_factory.get('PhotoUsage')
    print(f"  Photo / Camera Usage   : {format_bytes(photo_bytes)}")

    print("\n[BATTERY & POWER TELEMETRY]")
    print(f"  Current Capacity       : {batt_dom.get('BatteryCurrentCapacity', b_diag.get('CurrentCapacity', 'N/A'))}%")
    print(f"  Is Charging            : {batt_dom.get('BatteryIsCharging')}")
    if b_diag:
        print(f"  Cycle Count            : {b_diag.get('CycleCount', 'N/A')}")
        print(f"  Design Capacity        : {b_diag.get('DesignCapacity', 'N/A')} mAh")
        print(f"  Nominal Charge Cap     : {b_diag.get('NominalChargeCapacity', 'N/A')} mAh")
        print(f"  Instant Voltage        : {b_diag.get('Voltage', 'N/A')} mV")
        print(f"  Instant Amperage       : {b_diag.get('InstantAmperage', 'N/A')} mA")
        temp_raw = b_diag.get("Temperature")
        if isinstance(temp_raw, (int, float)):
            print(f"  Temperature            : {temp_raw / 100.0:.2f} °C")

    # =========================================================================
    # SECTION 2 & SECTION 3: SUMMARY (-s) vs FULL DEFAULT VIEW
    # =========================================================================
    if args.summary:
        print_section_header(f"SECTION 2: LOCKDOWN INFO SUMMARY ({len(lockdown_info)} Total Keys Captured)")
        print("  (Run without '-s / --summary' to display all individual lockdown keys)")

        print_section_header(f"SECTION 3: CAPTURED LOCKDOWN SUB-DOMAINS ({len(full_report['domains'])} Domains)")
        if full_report["domains"]:
            for dom_name in sorted(full_report["domains"].keys()):
                dom_val = full_report["domains"][dom_name]
                key_count = f"({len(dom_val)} keys)" if isinstance(dom_val, dict) else ""
                print(f"  • {dom_name:<42} {key_count}")
        else:
            print("  • None (Device is Untrusted / Unpaired)")
    else:
        print_section_header(f"SECTION 2: ALL 'lockdown info' KEYS ({len(lockdown_info)} Total Keys)")
        for k in sorted(lockdown_info.keys()):
            print(f"  {k:<38} : {format_val(lockdown_info[k])}")

        print_section_header(f"SECTION 3: CAPTURED LOCKDOWN SUB-DOMAINS ({len(full_report['domains'])} Domains)")
        if full_report["domains"]:
            for dom_name in sorted(full_report["domains"].keys()):
                dom_val = full_report["domains"][dom_name]
                print(f"\n  [{dom_name}]")
                if isinstance(dom_val, dict):
                    for dk in sorted(dom_val.keys()):
                        print(f"    {dk:<36} : {format_val(dom_val[dk])}")
                else:
                    print(f"    {format_val(dom_val)}")
        else:
            print("  • None (Device is Untrusted / Unpaired)")

    # =========================================================================
    # SHARED FOOTER BANNER
    # =========================================================================
    print("\n" + BANNER)
    print(f"[✓] Complete raw JSON saved to:")
    print(f"    {out_file}")
    print(f"    (Contains {len(lockdown_info)} root keys + {len(full_report['domains'])} domains | Paired={is_trusted_session})")
    print(BANNER)

if __name__ == "__main__":
    main()
