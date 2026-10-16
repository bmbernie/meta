# meta

A home for standalone utilities, one-off scripts, and diagnostic tools that are useful enough to version control, but too small to warrant their own dedicated repository.

## Repository Structure

Scripts are organized into subdirectories by platform or domain:

```text
meta/
└── apple/
    └── ios_enumerate.py
```

### `ios_enumerate.py`

A macOS command-line utility that interfaces with USB-connected iPhones via pymobiledevice3 to extract, display, and export a comprehensive inventory of hardware identifiers, firmware, storage, battery telemetry, and lockdownd domains.

```sh
# Full enumeration (prints executive summary, all lockdown keys, and all sub-domains)
python3 apple/ios_enumerate.py

# Summary mode (prints executive summary and active sub-domain list only)
python3 apple/ios_enumerate.py -s

# View full documentation and options
python3 apple/ios_enumerate.py --help
```

- **Output Trusted**: `/tmp/iphone_<UDID_info.json>`
- **Output Untrusted**: `/tmp/iphone_<UDID_untrusted_info.json>`
