
# WAYFINDER Prototype

This package completes the current BAN 8900 sprint tasks at prototype level.

## What the app demonstrates

- Three configured personas:
  - Family of 4
  - Woman, age 19, traveling alone
  - Man, age 27, traveling alone
- Green Book place evidence
- Persona-specific stop selection
- Dynamic conditions
- Decision log: Decision → Evidence → Uncertainty → Choice → Consequence
- Traveler memory that can influence later recommendations
- "Why here?" explanation
- "What if?" counterfactual
- Three-persona conversation
- Optional OpenAI Responses API mode
- Optional Mapbox geocoding + road-route display
- Google Maps driving-directions fallback
- SQLite journey/memory storage

## Run on Windows

1. Install Python 3.11+.
2. Unzip this folder.
3. Open Command Prompt in the folder.
4. Run:
   `run_wayfinder.bat`

Or manually:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Optional environment variables

### OpenAI
Set `OPENAI_API_KEY` to enable API-generated persona conversation.
You can also set `OPENAI_MODEL` to a model available to your API project.

### Mapbox
Set `MAPBOX_TOKEN` to enable embedded geocoding and road-route geometry.

Without Mapbox, the app still provides a Google Maps driving-directions link.

## Prototype limitations

- Historical Green Book listing does not prove a location or surrounding area was universally safe.
- Current Mapbox/Google road routing uses today's road network, not 1949 road reconstruction.
- Historical addresses may need geocoding review because streets, numbering, and businesses changed.
- The persona settings are design assumptions for the class prototype, not generalizations about real people.
