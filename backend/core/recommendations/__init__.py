"""Recommendation & Collection Completion engine.

See docs/RECOMMENDATION_ARCHITECTURE.md for the full design. This package is
intentionally separate from backend/core/comparer.py and the replacement
pipeline: RecommendationCandidate rows are never Movie rows, and nothing in
this package ever triggers a download or file replacement. Every acquisition
path (Radarr, Sonarr, Seerr) is an explicit, user-initiated hand-off.
"""
