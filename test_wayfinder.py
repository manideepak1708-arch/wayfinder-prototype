
from pathlib import Path
import tempfile
from wayfinder_core import *

def run():
    tmp = Path(tempfile.gettempdir()) / "wayfinder_test.db"
    if tmp.exists():
        tmp.unlink()
    init_db(tmp)
    personas = {p["persona_id"]:p for p in load_personas()}

    fam = choose_route(personas["P001"], path=tmp)
    woman = choose_route(personas["P002"], path=tmp)
    man = choose_route(personas["P003"], path=tmp)

    assert len(fam) == 5 and len(woman) == 5 and len(man) == 5
    nightlife = {"Tavern","Night Club","Bar","Liquor Store"}
    assert not any(p["category"] in nightlife for p in fam)
    assert {"Drug Store","Garage","Service Station"}.issubset({p["category"] for p in fam[1:-1]})
    assert not any(p["category"] in nightlife for p in woman)
    assert any(p["category"] == "Service Station" for p in woman[1:-1])
    assert any(p["category"] in nightlife for p in man[1:-1])

    target = next(p for p in load_places() if p["place_id"]=="CHI002")
    before = place_score(personas["P001"], target, tmp)
    add_memory("P001","CHI002",5,note="Preferred after a positive experience",path=tmp)
    after = place_score(personas["P001"], target, tmp)
    assert after > before

    dec = decision_rows(personas["P001"], fam, "Road delay", tmp)
    assert len(dec) == 3
    for d in dec:
        for key in ["Evidence","Uncertainty","Choice","Consequence","Confidence"]:
            assert key in d
    assert "Travel time increased" in dec[0]["Consequence"]

    url = google_maps_link(fam)
    assert url.startswith("https://www.google.com/maps/dir/?api=1")

    convo = simulated_persona_conversation(fam)
    assert len(convo)==3
    speakers = {x["speaker"] for x in convo}
    assert speakers == {"Family of 4","Woman, 19","Man, 27"}

    print("PASS: 8 core prototype tests")
    print("Family:", " -> ".join(p["name"] for p in fam))
    print("Woman 19:", " -> ".join(p["name"] for p in woman))
    print("Man 27:", " -> ".join(p["name"] for p in man))
    print("Memory score increased:", round(before,2), "->", round(after,2))

if __name__ == "__main__":
    run()
