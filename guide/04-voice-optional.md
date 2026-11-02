# 4. Voice (optional)

Mantle agents can talk. The Inspector has a voice mode, so you can speak to the foreman — or your travel
agent — instead of typing.

In the room, find a quiet corner first: fifty people talking to laptops gets loud.

## Turn it on

1. Get a speech key. The simplest is [Deepgram](https://deepgram.com) (it has free credit).
2. Add it to `.env` in the repo:

   ```bash
   DEEPGRAM_API_KEY=...
   ```

3. Restart: `Ctrl-C`, then `uv run workshop up`.
4. In the Inspector, leave the message box empty and select **Start voice conversation** (the waveform
   button). Allow microphone access when the browser asks.

With only `DEEPGRAM_API_KEY` set, the Inspector uses Deepgram's default English models. To choose
providers yourself, add `asr:` and `tts:` to the `inspector` channel in `integrations.yml`, for example
Deepgram Flux for better turn-taking:

```yaml
channels:
  inspector:
    enabled: true
    asr:
      name: deepgram
      language_map:
        en:
          language: en
          model: flux-general-en
    tts:
      name: deepgram
```

Other providers (Azure, Speechmatics, Cartesia, Rime, ElevenLabs) are listed in the Mantle docs under
*Speech providers*. Your skills don't change: Mantle tells the model to speak in short sentences when
it's on a voice call.
