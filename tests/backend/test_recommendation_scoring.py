import unittest

from backend.core.recommendations.scoring import CandidateSignals, score_candidate


class HardExclusionTests(unittest.TestCase):
    """Each of these must short-circuit to score=0 with exactly one reason,
    and never accidentally fall through to the positive-signal scoring below."""

    def test_already_in_plex_excludes_regardless_of_other_positive_signals(self):
        result = score_candidate(CandidateSignals(
            already_in_plex=True,
            collection_name="Toy Story Collection",
            collection_total_count=4,
            popularity=500.0,
        ))
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.state, "already_available")
        self.assertEqual(len(result.reasons), 1)
        self.assertEqual(result.reasons[0].reason_code, "already_in_plex")

    def test_already_managed_in_radarr_excludes(self):
        result = score_candidate(CandidateSignals(already_managed_radarr=True))
        self.assertEqual(result.state, "already_managed")
        self.assertEqual(result.reasons[0].reason_code, "already_managed_radarr")

    def test_already_managed_in_sonarr_excludes(self):
        result = score_candidate(CandidateSignals(already_managed_sonarr=True))
        self.assertEqual(result.state, "already_managed")
        self.assertEqual(result.reasons[0].reason_code, "already_managed_sonarr")

    def test_permanently_hidden_excludes(self):
        result = score_candidate(CandidateSignals(permanently_hidden=True, popularity=1000.0))
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.state, "excluded")

    def test_previously_dismissed_excludes(self):
        result = score_candidate(CandidateSignals(previously_dismissed=True, on_watchlist=True))
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.state, "excluded")

    def test_blocked_keyword_excludes_and_names_the_keyword(self):
        result = score_candidate(CandidateSignals(blocked_keyword_match="found footage"))
        self.assertIn("found footage", result.reasons[0].explanation)

    def test_blocked_person_excludes_and_names_the_person(self):
        result = score_candidate(CandidateSignals(blocked_person_match="Some Director"))
        self.assertIn("Some Director", result.reasons[0].explanation)

    def test_unsupported_media_type_excludes(self):
        result = score_candidate(CandidateSignals(unsupported_media_type=True))
        self.assertEqual(result.state, "excluded")

    def test_excluded_genre_match_excludes_and_names_the_genre(self):
        result = score_candidate(CandidateSignals(excluded_genre_match="Horror"))
        self.assertEqual(result.state, "excluded")
        self.assertIn("Horror", result.reasons[0].explanation)

    def test_exclusions_take_priority_in_a_fixed_order_when_multiple_apply(self):
        # already_in_plex is checked first — a title can't be simultaneously
        # "already available" and "already managed" in a way that matters to
        # the user, so the check order just needs to be stable and documented.
        result = score_candidate(CandidateSignals(already_in_plex=True, already_managed_radarr=True))
        self.assertEqual(result.state, "already_available")


class PositiveScoringTests(unittest.TestCase):
    def test_missing_collection_member_scores_higher_with_more_owned_siblings(self):
        few_owned = score_candidate(CandidateSignals(
            collection_name="X Collection", collection_owned_count=1, collection_total_count=5,
        ))
        many_owned = score_candidate(CandidateSignals(
            collection_name="X Collection", collection_owned_count=4, collection_total_count=5,
        ))
        self.assertGreater(many_owned.score, few_owned.score)
        self.assertEqual(few_owned.state, "active")
        self.assertEqual(few_owned.reasons[0].reason_code, "missing_collection_member")

    def test_sequel_prequel_reason_names_the_source_title(self):
        result = score_candidate(CandidateSignals(
            is_sequel_or_prequel=True,
            sequel_source_title="The Little Mermaid",
            sequel_source_movie_id=42,
        ))
        self.assertGreater(result.score, 0)
        reason = next(r for r in result.reasons if r.reason_code == "direct_sequel")
        self.assertIn("The Little Mermaid", reason.explanation)
        self.assertEqual(reason.source_movie_id, 42)

    def test_related_titles_each_contribute_their_own_reason(self):
        result = score_candidate(CandidateSignals(
            related_source_titles=("Movie A", "Movie B"),
        ))
        related_reasons = [r for r in result.reasons if r.reason_code == "related_to_library_title"]
        self.assertEqual(len(related_reasons), 2)

    def test_genre_affinity_scales_with_number_of_matched_genres(self):
        one_genre = score_candidate(CandidateSignals(genre_matches=("Animation",)))
        two_genres = score_candidate(CandidateSignals(genre_matches=("Animation", "Family")))
        self.assertGreater(two_genres.score, one_genre.score)

    def test_watchlist_presence_contributes_a_reason(self):
        result = score_candidate(CandidateSignals(on_watchlist=True))
        self.assertEqual(result.reasons[0].reason_code, "on_watchlist")
        self.assertGreater(result.score, 0)

    def test_recent_activity_only_scored_when_signal_present(self):
        with_activity = score_candidate(CandidateSignals(recent_source_activity=True))
        without_activity = score_candidate(CandidateSignals(recent_source_activity=False))
        self.assertGreater(with_activity.score, without_activity.score)
        self.assertEqual(without_activity.score, 0.0)

    def test_streaming_availability_names_the_provider(self):
        result = score_candidate(CandidateSignals(
            available_on_subscribed_provider=True,
            available_provider_names=("Disney+",),
        ))
        reason = next(r for r in result.reasons if r.reason_code == "streaming_available")
        self.assertIn("Disney+", reason.explanation)

    def test_streaming_flag_without_provider_names_does_not_add_a_reason(self):
        # Defensive: available_on_subscribed_provider=True with an empty name
        # tuple shouldn't produce an empty/garbled reason string.
        result = score_candidate(CandidateSignals(available_on_subscribed_provider=True))
        self.assertEqual(result.reasons, [])

    def test_popularity_alone_is_never_treated_as_personal_preference(self):
        """Popularity must contribute far less than a real relationship
        signal like a missing collection member — otherwise a merely popular
        unrelated title could outscore a genuine collection gap."""
        popularity_only = score_candidate(CandidateSignals(popularity=100000.0))
        collection_gap = score_candidate(CandidateSignals(
            collection_name="Some Collection", collection_owned_count=2, collection_total_count=3,
        ))
        self.assertLess(popularity_only.score, collection_gap.score)

    def test_popularity_contribution_is_capped(self):
        moderate = score_candidate(CandidateSignals(popularity=500.0))
        extreme = score_candidate(CandidateSignals(popularity=50000.0))
        self.assertEqual(moderate.score, extreme.score)

    def test_rating_contribution_is_bounded_by_the_0_to_10_scale(self):
        result = score_candidate(CandidateSignals(vote_average=10.0))
        self.assertLessEqual(result.score, 8.0)  # _WEIGHT_RATING_MAX


class NegativeSignalTests(unittest.TestCase):
    def test_outside_year_range_reduces_but_does_not_exclude(self):
        base = score_candidate(CandidateSignals(on_watchlist=True))
        penalized = score_candidate(CandidateSignals(on_watchlist=True, outside_year_range=True))
        self.assertLess(penalized.score, base.score)
        self.assertEqual(penalized.state, "active")

    def test_score_never_goes_negative(self):
        result = score_candidate(CandidateSignals(
            outside_year_range=True,
            outside_language_preference=True,
            unavailable_in_configured_region=True,
        ))
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.state, "active")  # penalized, not excluded

    def test_no_signals_at_all_scores_zero_with_no_reasons(self):
        result = score_candidate(CandidateSignals())
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.reasons, [])
        self.assertEqual(result.state, "active")


if __name__ == "__main__":
    unittest.main()
