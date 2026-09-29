from consensus.pos.blockchain_structures import elect_leader, election_details


def test_election_details_explains_the_same_leader_elect_leader_picks():
    stakes = {"pk-b": 30, "pk-a": 10, "pk-c": 60}
    details = election_details("some-seed", stakes)

    assert details["total"] == 100
    assert details["leader"] == elect_leader("some-seed", stakes)
    # Ranges tile [0, total) in public-key order and the pick lies in the leader's range.
    assert [r["staker"] for r in details["ranges"]] == ["pk-a", "pk-b", "pk-c"]
    assert details["ranges"][0]["start"] == 0 and details["ranges"][-1]["end"] == 100
    leader_range = next(r for r in details["ranges"] if r["staker"] == details["leader"])
    assert leader_range["start"] <= details["pick"] < leader_range["end"]


def test_election_details_with_no_stakes_has_no_leader():
    details = election_details("s", {})
    assert details["leader"] is None and details["pick"] is None and details["ranges"] == []
    assert elect_leader("s", {"pk": 0}) is None
