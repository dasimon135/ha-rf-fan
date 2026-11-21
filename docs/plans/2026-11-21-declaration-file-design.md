# A fan's declaration as one file (#58)

Validated with the maintainer on 2026-11-21.

## Goal

Export a fan's declaration (capabilities, free-form key names, repeat count and
learned codes) as one YAML document, and create or replace a fan from a pasted one.
Three uses: setting up several identical units, backup and restore, and sharing a
known-good declaration for a given remote model.

## The file

```yaml
format: 1
name: Living room fan
speed_count: 6
light_control: toggle
has_fan_on: false
# ... every other declaration key, spelled as in the entry data
extra_names: {extra_1: Ionisation}
repeat_count: 3
codes:
  speed_1: "raw:..."
```

- No gateway, no runtime state. The gateway belongs to one installation; leaving it
  out is what makes the file shareable.
- Keys are the entry-data keys, so export is a filter of `entry.data` and import
  goes through `_read_declaration`, the reader the declaration form already uses:
  same defaults, same refusals.
- Parsed with `yaml.safe_load`, size-capped. An unknown key, an invalid value, a
  code for an action the declaration does not have, a non-string code, or a
  duplicated code is refused, and the error names the offending key.

## Flow

- **Adding a fan**: the first screen becomes a menu, *Declare it by hand* (the
  existing form) or *Paste a declaration* (gateway, name, text). Required codes the
  file lacks go through the usual manual-or-learn choice, for those keys only.
- **Reconfigure** gains two entries:
  - *Export the declaration* shows the YAML in a code block and closes without
    changing anything.
  - *Replace with a pasted declaration* keeps the entry's gateway and name,
    replaces capabilities and codes, then asks for the missing keys.

## Not done

No action/service for export (one more surface to maintain), no library of
per-remote files in the repository.

## Tests

A pure `declaration.py` (read and write) with its own tests; an export → import
round trip that must give back the same data; flow tests for the add and
reconfigure paths.
