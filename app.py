
import os
import pandas as pd
import streamlit as st

from wayfinder_core import (
    init_db, load_personas, choose_route, google_maps_link, decision_rows, save_journey,
    add_memory, memory_summary, simulated_persona_conversation, openai_persona_conversation,
    mapbox_route_geometry, build_counterfactual
)

st.set_page_config(page_title="WAYFINDER Prototype", page_icon="🧭", layout="wide")
init_db()

st.title("🧭 WAYFINDER — Living Map Prototype")
st.caption("Historical Green Book evidence + persona decisions + memory + adaptation. Prototype routes use current road APIs when enabled.")

personas = load_personas()
persona_names = [p["name"] for p in personas]
selected_name = st.sidebar.selectbox("Traveler persona", persona_names)
persona = next(p for p in personas if p["name"] == selected_name)

st.sidebar.subheader("Traveler state")
safety = st.sidebar.slider("Safety priority", 1, 5, persona["safety"])
cost = st.sidebar.slider("Cost priority", 1, 5, persona["cost"])
speed = st.sidebar.slider("Speed priority", 1, 5, persona["speed"])
entertainment = st.sidebar.slider("Entertainment priority", 1, 5, persona["entertainment"])
risk = st.sidebar.slider("Risk tolerance", 1, 5, persona["risk_tolerance"])
event = st.sidebar.selectbox("Dynamic condition", [
    "No dynamic event", "Gas becomes scarce", "Lodging becomes unavailable",
    "Trusted source warning", "Road delay"
])

persona = dict(persona)
persona.update({"safety":safety,"cost":cost,"speed":speed,"entertainment":entertainment,"risk_tolerance":risk})

top1, top2, top3 = st.columns(3)
top1.metric("Persona", persona["name"])
top2.metric("Safety priority", persona["safety"])
top3.metric("Risk tolerance", persona["risk_tolerance"])
st.info(persona["goal"])

if st.button("Generate Journey", type="primary"):
    st.session_state["route"] = choose_route(persona)
    st.session_state["decisions"] = decision_rows(persona, st.session_state["route"], event)
    st.session_state["persona"] = persona
    st.session_state["event"] = event

route = st.session_state.get("route")
decisions = st.session_state.get("decisions")

if route:
    st.subheader("Journey")
    st.write(" **→** ".join(p["name"] for p in route))
    st.link_button("Open actual driving directions in Google Maps", google_maps_link(route))

    mapbox_token = os.getenv("MAPBOX_TOKEN") or os.getenv("MAPBOX_ACCESS_TOKEN")
    if mapbox_token:
        try:
            geo = mapbox_route_geometry(route, mapbox_token)
            if geo:
                import pydeck as pdk
                points = [{"name":p["name"],"lon":lon,"lat":lat} for p,(lon,lat) in zip(route, geo["waypoints"])]
                path = [{"path":geo["coordinates"]}]
                layers = [
                    pdk.Layer("PathLayer", path, get_path="path", get_width=6, width_min_pixels=3, pickable=True),
                    pdk.Layer("ScatterplotLayer", points, get_position="[lon, lat]", get_radius=80, pickable=True),
                ]
                avg_lat = sum(x["lat"] for x in points)/len(points)
                avg_lon = sum(x["lon"] for x in points)/len(points)
                deck = pdk.Deck(
                    initial_view_state=pdk.ViewState(latitude=avg_lat, longitude=avg_lon, zoom=11),
                    layers=layers,
                    tooltip={"text":"{name}"},
                )
                st.pydeck_chart(deck, height=450)
                c1,c2 = st.columns(2)
                c1.metric("Route distance", f"{geo['distance_m']/1609.344:.1f} mi" if geo.get("distance_m") else "—")
                c2.metric("Estimated drive", f"{geo['duration_s']/60:.0f} min" if geo.get("duration_s") else "—")
        except Exception as e:
            st.warning(f"Mapbox route could not be displayed: {e}")
    else:
        st.warning("MAPBOX_TOKEN is not set, so the embedded road route is disabled. The Google Maps button above still opens driving directions.")

    st.subheader("Decision Log")
    st.dataframe(pd.DataFrame(decisions), width="stretch", hide_index=True)

    if st.button("Save this journey"):
        jid = save_journey(st.session_state["persona"], route, st.session_state["event"], decisions)
        st.success(f"Journey {jid} saved to the WAYFINDER memory database.")

    st.subheader("Why here?")
    selected_stop = st.selectbox("Choose a recommended stop", [p["name"] for p in route[1:-1]])
    row = next(d for d in decisions if d["Choice"] == selected_stop)
    st.write(f"**Evidence:** {row['Evidence']}")
    st.write(f"**Uncertainty:** {row['Uncertainty']}")
    st.write(f"**Decision reason:** {row['Why']}")
    st.write(f"**Confidence:** {row['Confidence']}")

    st.subheader("Traveler Memory")
    stop_for_memory = st.selectbox("Record experience at", [p["name"] for p in route[1:-1]], key="memstop")
    rating = st.slider("Experience rating", 1, 5, 4)
    note = st.text_input("Memory note", "Good experience; consider again on a future trip.")
    if st.button("Add memory"):
        place = next(p for p in route if p["name"] == stop_for_memory)
        add_memory(persona["persona_id"], place["place_id"], rating, note=note)
        st.success("Memory stored. Regenerate the journey to let prior experience affect future ranking.")

    ms = memory_summary(persona["persona_id"])
    if ms:
        st.dataframe(pd.DataFrame(ms), width="stretch", hide_index=True)

    st.subheader("What if?")
    cf_change = st.selectbox("Change one condition", [
        "Higher safety priority", "Higher entertainment priority", "Higher speed priority"
    ])
    if st.button("Run counterfactual"):
        cf_persona = build_counterfactual(persona, cf_change)
        cf_route = choose_route(cf_persona)
        c1,c2 = st.columns(2)
        with c1:
            st.markdown("**Original journey**")
            st.write(" → ".join(p["name"] for p in route))
        with c2:
            st.markdown(f"**Counterfactual: {cf_change}**")
            st.write(" → ".join(p["name"] for p in cf_route))

    st.subheader("Three-Persona Conversation")
    st.caption("The prototype can run in deterministic simulation mode, or call the OpenAI Responses API when OPENAI_API_KEY is configured.")
    use_openai = st.toggle("Use OpenAI API for the conversation", value=False)
    if use_openai:
        text = openai_persona_conversation(route)
        if text:
            st.write(text)
        else:
            st.warning("OPENAI_API_KEY is not configured. Showing simulation mode instead.")
            for turn in simulated_persona_conversation(route):
                with st.chat_message("assistant"):
                    st.markdown(f"**{turn['speaker']}** — {turn['message']}")
    else:
        for turn in simulated_persona_conversation(route):
            with st.chat_message("assistant"):
                st.markdown(f"**{turn['speaker']}** — {turn['message']}")

st.divider()
st.caption("Important: Green Book listing = historical evidence of being listed; it is not proof that a surrounding area was universally safe. Modern routing APIs use today's road network, not reconstructed 1949 roads.")
