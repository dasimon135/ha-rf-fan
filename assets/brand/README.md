# Brand assets

Integration icon/logo for the `rf_fan` custom integration.

- `icon.png` — 256×256, rounded-square gradient with a fan glyph + RF waves.
- `icon@2x.png` — 512×512 (same, high-res).
- `logo.png` — horizontal lockup (icon + "RF Fan" wordmark), 256 high.

## Making them show up in Home Assistant

Home Assistant serves integration brand images from the
[home-assistant/brands](https://github.com/home-assistant/brands) repository, **not**
from the component. Until submitted, the UI shows "logo not available".

To publish, open a PR to `home-assistant/brands` placing:

```
custom_integrations/rf_fan/icon.png     (256×256)
custom_integrations/rf_fan/icon@2x.png  (512×512)
custom_integrations/rf_fan/logo.png     (optional)
```

Requirements: PNG, trimmed, transparent background where applicable. See the brands
repo README for the current rules before submitting.

Regenerate with `scratchpad/make_icon.py` (Pillow).
