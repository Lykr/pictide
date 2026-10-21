# Candidate Tag Libraries and Presets

[简体中文](../../../zh-CN/dev/reference/api/candidate.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

## Library file management

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/candidate/library` | None | `{selected,libraries:[{filename,tag_count,relation_count,bytes}]}` |
| POST | `/api/candidate/library` | multipart/form-data, field `file`, `.sqlite3` or `.sqlite3.gz` | 201; `{filename,tag_count,relation_count,bytes}` |
| PUT | `/api/candidate/library` | JSON `{filename}` | `{selected}`; takes effect immediately |

Files are stored in `libraries/` under the selected data directory. GET refreshes the directory and selected file status. A valid file requires the tags, correlations, and dataset tables, a source status of ready, and dataset.min_cooccurrence as a positive-integer lower bound for relations retained in the library. Uploads and gzip decompression each support a maximum of 2 GiB. Duplicate filenames are automatically numbered, and only statistical tables are copied. After a successful upload, the page calls PUT to select the file automatically. The selection is saved in the personal configuration database; existing presets, jobs, and prefetched results are preserved. Status changes reuse the candidate event.

## Candidate tag library, presets, and previews

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/candidate/tags` | `query`, `page=1`, `page_size=15` (1–200) | `{tags:[{id,name,post_count}],total,page,page_size}` |
| GET | `/api/candidate/dataset` | None | Data status, source, revision, total image count, `tag_count`, and library lower bound `min_cooccurrence` |
| GET | `/api/candidate/presets` | None | `{presets:[{id,name}]}` |
| GET | `/api/candidate/presets/{id}` | None | `{id,name,document}` |
| POST | `/api/candidate/presets` | `{name,document,id?}` | Saved `{id,name,document}` |
| DELETE | `/api/candidate/presets/{id}` | `{}` | `{deleted:boolean,id}` |
| POST | `/api/candidate/generate` | Candidate generation parameters | Complete combination and report |
| POST | `/api/candidate/relations` | `{anchor,terms:[complete terms]}` | `{anchor:{text,known},relations:[{text,known,pmi,count}]}` |

The library is read-only, with no HTTP endpoints for adding, editing, or deleting library terms. Original names retain underscores, such as black_hair. Search treats spaces as equivalent and sorts by descending frequency, then by name for ties. Final candidate output uses comma-separated terms with spaces between words.

Preset POST creates a preset when id is omitted and updates one when an existing id is provided. Presets contain editable fixed terms and co-occurrence parameters; they do not modify the read-only library. Saving and generation both use max(preset minimum co-occurrence count, current library lower bound). Switching libraries preserves saved presets; the page only raises insufficient draft values automatically, and writes them only on save.

### Preset document

When the personal preset store is empty, startup creates the `default` preset with `base_positive:["general"]` and `base_negative:[]`. Existing presets are preserved. The field defaults below apply when validating a submitted document with omitted fields; explicitly empty arrays remain empty.

| Field | Range | Default |
| --- | --- | --- |
| `base_positive` / `base_negative` | Arrays of complete term strings; custom text is allowed | `[]` |
| `min_tags` | Integer 1–1000 | 10 |
| `max_tags` | Integer min_tags–1000 | 30 |
| `pmi_threshold` | Finite number | 0 |
| `min_cooccurrence` | Positive integer up to the maximum safe integer; the effective value is at least the current library lower bound | max(10, library lower bound) |
| `change_budget` | Integer 0–2000 | 2 |
| `blocked_keywords` | Array of keyword strings | `[]` |

The number of fixed positive terms must not exceed max_tags. Newly added positive terms must satisfy PMI and minimum co-occurrence requirements with existing positive terms from the library. Custom fixed terms have no statistics and do not participate in correlation thresholds. Negative terms do not participate in PMI comparisons, but automatic selection excludes terms whose full names match entries in the negative list (case-insensitive, treating spaces and underscores as equivalent); explicitly fixed positive terms are retained. Keywords filter only newly selected terms, with case-insensitive matching and equivalence between spaces and underscores.

### Candidate generation parameters

| Field | Range and default |
| --- | --- |
| `preset_id` | Required, nonempty preset ID |
| `mode` | `random_each_run / fixed_seed / sequence`; default random_each_run |
| `seed` | Integer 0–9007199254740991; default 0; prompt seed |
| `sequence_step` | Integer 0–1000; default 0; used only by sequence |
| `max_steps` | Integer 1–1000000; 100 when omitted; expansion search limit for all modes |
| `seed_control` / `step_control` | `fixed / increment / decrement / randomize`; default fixed |
| `document` | Optional preset draft that overrides the saved preset contents |

Post-generation controls advance the parameters for the next round during multi-round job generation. A single preview returns the current result without advancing automatically. random_each_run creates a new prompt seed on every generation; the image seed is configured separately in the job request.

The response includes `positive,negative,seed,selected_tags,candidate_id,source_id,preset_id,mode,report`. Each selected_tags item contains `id,text,categories,channel,source_id`. `report` is `{stop_reason,tag_count,unrecognized_fixed}`; sequence additionally includes `{seed,step,change_budget,changes}`.

The target length is sampled uniformly between the lower and upper bounds. When co-occurrence is insufficient or the search limit is reached, the current combination is returned; failing to reach the target length does not cause an error. Possible stop_reason values are `target_length,search_limit,no_eligible_tags,budget_zero`. Data that is not ready and invalid parameters still produce errors.

Relations only queries relationships among the current terms and does not create a generation job. A missing record for a pair of known terms means its statistics were not retained, and pmi/count are null. The current trial library retains relations with co-occurrence ≥1,000. Custom terms have known=false and no statistics. Do not interpret null as zero co-occurrence or PMI=0.
