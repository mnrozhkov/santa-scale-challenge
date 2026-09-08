# Santa Scale Challenge

Workshop media-gen: a participant's own Nebius account turns kid profiles into gift cards, then into videos, at batch scale.

## Language

**KidProfile**:
A child Santa is writing a card for: name, age (1–18), and wishlist.
_Avoid_: kid row, CSV record, user, child account

**GiftCard**:
The finished card: gift recommendation, wish, illustration, plus the rendered PNG and HTML.
_Avoid_: card image (the illustration alone), PNG, poster

**Wish**:
The personalized holiday message on a GiftCard, including one mood tag for music.
_Avoid_: message, copy, prompt

**role**:
A named model slot the code asks for (`llm`, `image`, `video`, `audio`). The concrete model lives in yaml, not in code.
_Avoid_: model, endpoint (an endpoint *hosts* a role)

**adapter**:
The API shape used to call a role (`openai_chat`, `openai_images`, `wan_omni`, `openai_video`, `acestep_audio`, `local_tracks`).
_Avoid_: client, provider, SDK wrapper

**fallback**:
The secondary adapter for a role when the primary is missing or fails (OpenAI by default; audio uses bundled tracks).
_Avoid_: backup, offline (offline copies files and calls no model)

**offline**:
A CLI mode that copies bundled fallback files and does not call endpoints or Jobs.
_Avoid_: fallback, dry-run

**run**:
One `santa batch` execution: N kids, K jobs, one summary.
_Avoid_: job, batch (batch is the command)

**chunk**:
The list of card ids one GPU Job processes inside a run.
_Avoid_: shard, partition, slice

**mood bank**:
A small set of pre-generated instrumental tracks, one per mood tag, that a Job picks instead of synthesizing music per card.
_Avoid_: playlist, soundtrack, ACE-Step (the audio role that can *fill* the bank)

**wall**:
The service page that lists published cards and videos from the participant's bucket.
_Avoid_: gallery, feed, dashboard
