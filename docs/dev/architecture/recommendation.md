# Recommendation Module

[简体中文](../../zh-CN/dev/architecture/recommendation.md)

[Architecture Overview](../architecture.md) · [Recommendation HTTP API](../reference/api/preferences.md)

Recommendation receives complete candidate combinations and returns scores. It does not generate candidates or call Task. Start with responsibilities, then read the feature flow and model preparation as needed.

## Internal Recommendation Architecture

Recommendation receives complete candidate prompt combinations and feedback only through App. Its scoring unit is a combination. Library IDs and categories do not form part of recommendation content identity; identical text with the same positive/negative polarity uses the same content features.

The architecture diagram shows logical components and call dependencies only. Arrows indicate calls or dependencies, not the temporal order of data flow. These are internal responsibilities, without a requirement for separate processes or services.

```mermaid
flowchart TD
    App["Application orchestration"]
    subgraph Rec["Recommendation module"]
        Service["Recommendation application service: scoring entry / feedback entry"]
        Features["Feature encoder"]
        Scorer["Scoring policy: Thompson Sampling / posterior mean"]
        Learner["Preference learner"]
        Model["Text encoding model adapter"]
        Cache["Semantic vector cache interface"]
        State["User preference state storage interface"]
        Service --> Features
        Service --> Scorer
        Service --> Learner
        Features --> Model
        Features --> Cache
        Scorer --> State
        Learner --> State
    end
    App --> Service
```

The recommendation application service coordinates encoding, scoring, and learning internally. For scoring, it obtains combination features and calls the scoring policy. For feedback, it obtains features for the actual generated combination and passes them, the feedback, and record identifiers to the preference learner. These use cases are triggered separately. Recommendation does not call Candidate or Task, or directly read their implementations or tag library files. The model adapter encapsulates a fixed version of the text encoding model; persistence adapters implement the cache and preference state storage interfaces.

## Data Processing for Recommendation Scoring

The diagram below uses Standard strength to illustrate the data and processing steps in a scoring request. Tag content features, semantic vectors, and combination-level features are data products; content encoding, semantic encoding, and feature combination are processing steps. The feature encoder above handles these steps, implemented in `backend/recommendation/features.py` and `policy.py`.

```mermaid
flowchart TD
    Request[/"Candidate combinations / user / context"/] --> Prepare["Read complete positive/negative text and tag snapshot for each combination"]
    Prepare --> Identity["Normalize text and polarity; encode tag identity"]
    Identity --> Sparse[/"Specific tag features"/]
    Prepare --> Semantic["Query semantic cache; call encoding model for misses"]
    Semantic --> Vector[/"Semantic vectors"/]
    Sparse --> Combine["Build combination-level features"]
    Vector --> Combine
    Combine --> FeatureVector[/"Feature representation of each complete combination"/]
    UserState[/"Current user's preference state"/] --> Sample["Sample preference parameters shared by this request"]
    FeatureVector --> Score["Compute combination scores"]
    Sample --> Score
    Score --> Response[/"Scores keyed by combination ID"/]
```

The learning entry follows a separate flow: read the actual generated combination snapshot → use the same feature encoder version → associate combination features with user feedback → update preference state. A scoring request does not run this learning flow. [Module Call Sequence](flows.md#candidates-scoring-and-generation) describes the order of App's calls to Candidate, Recommendation, and Task; it complements the static architecture diagram.

- Combination IDs associate returned scores with App's combinations. Tag content identity supports learning and sharing experience across combinations. Normalized text and polarity define tag content identity; identical text under different IDs can reuse content features. Synonyms and antonyms retain their own specific tag features, and semantic vectors do not automatically merge preferences.
- Combination-level features comprise sparse features for specific tags and semantic vectors aggregated separately by positive/negative polarity. Only complete-combination scores are returned externally. Version 1 is a linear model and does not claim to have learned complex interactions.
- At Standard strength, all combinations in a request are compared using the same sampled preference parameters. Strong uses the posterior mean without sampling. After Recommendation returns scores, App selects a combination and calls Task, without calling Candidate again to sample tags by score.
- Frozen MiniLM encodes base tags. The vector cache includes text, model files, runtime dependencies, and preprocessing versions. User likes update preference state without training the text encoding model.
- Learning input is the actual generated combination and feedback supplied by App, using the text, polarity, and feature version at that time. Current categories or tag content do not replace history. A whole-image like/dislike learns +1/-1 for the combination, without directly turning it into independent feedback for every tag. Unrated remains unknown; withdrawal removes the corresponding contribution or replays valid feedback, rather than counting as negative feedback.
- User preference state is isolated by user and feature version. Changing encoders requires re-encoding and rebuilding state from valid historical feedback, without mixing vector spaces. The cache and policy state persist through storage interfaces in the application data directory. Current algorithms and boundaries are described below; replacing the encoding model requires separate design approval.

## Current Capabilities and Limitations

Version 1 implements offline MiniLM tag encoding on CPU, complete-combination scoring, Bayesian linear posterior sampling, explicit positive/negative feedback learning, withdrawal, and restart recovery. App first receives the candidate set, passes it to the recommendation service's `score`, then selects a combination and submits a task. The old `choose` interface and Recommendation's type imports from Candidate have been removed; recommendation owns its framework-independent contracts in `backend/recommendation/contracts.py`.

Learning associates explicit positive/negative feedback with combinations; unrated remains unknown. Scores are not like probabilities. Exposure/non-conversion learning, complex interactions, and image features are not implemented. Missing or unavailable models are reported as status; App retains its existing default candidate handling, and fallback is not called learning. Bootstrap's `recommendation` reports availability and version, while `preference_learning` reflects actual availability. Unapplied learning notifications remain pending for retry without rolling back user feedback. Preference inspection and reset reuse Web → Host → App → Recommendation → Store. Inspection reads current learning state only. Reset atomically clears preferences for all feature versions and records a feedback-event boundary, retaining images and feedback.

## Scoring and Feedback at Runtime

Standard uses Thompson Sampling; Strong uses deterministic posterior means. Both share user preferences. App selects the highest-scoring complete combination without returning scores to Candidate for reassembly. Specific tag identities and semantic features both participate in linear scoring; synonymous or antonymous tags do not automatically merge.

Feedback and pending learning records are saved in the same transaction before returning immediately. App's single background learning worker processes persisted records. Scoring uses only completed preference state and does not wait for the current feedback to be learned. When the model is unavailable, feedback remains for later processing; a new feedback event does not invalidate existing prefetch.

Preference scores in image information reuse a deterministic raw-score cache; an existing cache is recomputed only by manual refresh. The UI's 0–100 scale is relative to the historical score range, not a probability of liking. See the [Scoring API](../reference/api/images.md#like-filters-and-image-preference-scores).

## Recommendation Dependency Preparation

Recommendation depends on [MiniLM](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx) for text embeddings, using offline FastEmbed-format ONNX files. `backend/recommendation/model.json` is the single catalog for the fixed source revision, five required files, byte sizes, and SHA-256 values. `backend/recommendation/resources.py` prepares and verifies these files in the selected data directory's `models/minilm/`. It resumes partial downloads and preserves existing invalid files in a backup before replacing them successfully.

Source and portable startup share `PictideApplication.prepare_startup()` in `backend/application.py`: initialize any bundled library, then prepare the model. Host creates the HTTP service and opens the page only after preparation succeeds. A model download or verification failure stops startup; restarting retries with retained `.part` files. Valid local files allow offline startup. See [startup and offline model preparation](../../guides/getting-started.md#recommendation-dependency-preparation) for user instructions.

Portable builds carry the catalog and CPU inference dependencies (FastEmbed, ONNX Runtime, and tokenizers), without model weights or build-time model downloads. The encoder remains an offline reader; runtime encoder availability is reported through bootstrap's `recommendation` and roam responses. Python 3.12 has been validated; installers select compatible dependencies for older Python versions.

## Further Reading

- [User Preference Inspection, Export, and Reset API](../reference/api/preferences.md)
