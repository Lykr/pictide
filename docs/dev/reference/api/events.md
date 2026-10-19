# Bootstrap and Live Events

[简体中文](events.zh-CN.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

## Bootstrap and live events

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/bootstrap` | None | Initialization data; fields listed below |
| GET | `/api/events` | Persistent SSE connection | `event: change`; data is `{revision,topic}` |

Bootstrap includes `name,module,version,database_path,data_directory,backend_types,backends,jobs,artifacts,roam_view,roam_settings,artifact_revision,counts,artifact_page,recommendation,capabilities`. Backend configurations hide API keys. `jobs` contains the most recent 100 jobs, and `artifacts` contains the Roam window near the saved viewing position. General and history settings are read through their respective endpoints.

`recommendation` includes `available,model_version,feature_version,policy_version,error`. `capabilities` includes `generation,feedback,preference_learning,cooccurrence_prompts,prompt_sequences,events,roam_prefetch`.

The first SSE topic is `ready`. Subsequent topics may be `jobs,feedback,artifacts,backends,workflows,candidate,settings,roam_settings,general_settings,recommendation`. A comment heartbeat is sent after approximately 20 seconds without changes. These are refresh notifications: clients reread the relevant resources after receiving them. `revision` increments within the process and resets to zero on restart. There is no replay of historical events, and slow clients may receive only the latest notification.
