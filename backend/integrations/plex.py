"""Plex Media Server API client using python-plexapi."""
from __future__ import annotations

from typing import Optional

from backend.config import get_config


class PlexClient:
    def __init__(self) -> None:
        config = get_config()
        self.url = config.plex.url
        self.token = config.plex.token
        self.library_sections = config.plex.library_sections
        self._server = None

    def _get_server(self):
        if self._server is None:
            from plexapi.server import PlexServer
            self._server = PlexServer(self.url, self.token)
        return self._server

    def get_all_movies(self) -> list[dict]:
        """Scan configured sections and return a list of movie dicts."""
        server = self._get_server()
        movies = []
        sections = self.library_sections or [
            s.title for s in server.library.sections() if s.type == "movie"
        ]
        for section_name in sections:
            try:
                section = server.library.section(section_name)
            except Exception:
                continue
            for plex_movie in section.all():
                for media in plex_movie.media:
                    for part in media.parts:
                        imdb_id = ""
                        tmdb_id = 0
                        for guid in (plex_movie.guids or []):
                            gid = str(guid.id)
                            if gid.startswith("imdb://"):
                                imdb_id = gid.replace("imdb://", "")
                            elif gid.startswith("tmdb://"):
                                try:
                                    tmdb_id = int(gid.replace("tmdb://", ""))
                                except ValueError:
                                    pass

                        movies.append({
                            "plex_rating_key": str(plex_movie.ratingKey),
                            "title": plex_movie.title,
                            "year": plex_movie.year,
                            "imdb_id": imdb_id,
                            "tmdb_id": tmdb_id,
                            "file_path": part.file,
                            "file_size": part.size or 0,
                            "resolution": str(media.videoResolution or ""),
                            "video_codec": str(media.videoCodec or ""),
                            "audio_codec": str(media.audioCodec or ""),
                            "bitrate": media.bitrate or 0,
                            "container": str(media.container or ""),
                            "width": media.width or 0,
                            "height": media.height or 0,
                        })
        return movies

    def refresh_library(self, section_name: Optional[str] = None) -> None:
        server = self._get_server()
        if section_name:
            server.library.section(section_name).update()
        else:
            for name in self.library_sections:
                try:
                    server.library.section(name).update()
                except Exception:
                    pass

    def test_connection(self) -> dict:
        try:
            from plexapi.server import PlexServer
            server = PlexServer(self.url, self.token)
            sections = [s.title for s in server.library.sections()]
            return {
                "success": True,
                "server_name": server.friendlyName,
                "version": server.version,
                "sections": sections,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_shows(self) -> list[dict]:
        """
        Return all TV shows across all TV library sections with file size
        and watch history data.

        Uses batch fetching (one episodes search per section, one shows fetch
        per section) to minimise round-trips to the Plex server.

        Each dict has:
          plex_rating_key, title, year, total_size_bytes, episode_count,
          poster_path, last_watched_at (ISO string or None),
          watched_by (list of usernames who have any watch history),
          never_watched (bool)
        """
        server = self._get_server()
        shows: list[dict] = []

        tv_sections = [s for s in server.library.sections() if s.type == "show"]

        for section in tv_sections:
            # --- 1. Batch-fetch all episodes (single HTTP request) to sum sizes ---
            show_sizes: dict[str, int] = {}
            show_ep_counts: dict[str, int] = {}
            try:
                all_episodes = section.search(libtype="episode")
                for ep in all_episodes:
                    key = str(ep.grandparentRatingKey)
                    for media in ep.media:
                        for part in media.parts:
                            show_sizes[key] = show_sizes.get(key, 0) + (part.size or 0)
                    show_ep_counts[key] = show_ep_counts.get(key, 0) + 1
            except Exception:
                pass  # fall back to per-show episode iteration below

            # --- 2. Iterate shows (already loaded by section.all()) ---
            for show in section.all():
                key = str(show.ratingKey)

                total_size = show_sizes.get(key, 0)
                episode_count = show_ep_counts.get(key, 0)

                # Fall back to per-show episode iteration if batch failed
                if total_size == 0 and episode_count == 0:
                    for episode in show.episodes():
                        for media in episode.media:
                            for part in media.parts:
                                total_size += part.size or 0
                        episode_count += 1

                # --- 3. Watch history per show ---
                last_watched_at = None
                watched_by: list[str] = []
                try:
                    history = show.history()
                    for entry in history:
                        username = (
                            getattr(entry, "username", None)
                            or str(getattr(entry, "accountID", "unknown"))
                        )
                        if username not in watched_by:
                            watched_by.append(username)
                        viewed_at = getattr(entry, "viewedAt", None)
                        if viewed_at is not None:
                            ts = viewed_at.isoformat() if hasattr(viewed_at, "isoformat") else str(viewed_at)
                            if last_watched_at is None or ts > last_watched_at:
                                last_watched_at = ts
                except Exception:
                    pass  # history() may fail on managed accounts or restricted servers

                # Extract IDs from guids
                tvdb_id = None
                imdb_id = None
                for guid in (show.guids or []):
                    gid = str(guid.id)
                    if gid.startswith("tvdb://"):
                        try:
                            tvdb_id = int(gid.replace("tvdb://", ""))
                        except ValueError:
                            pass
                    elif gid.startswith("imdb://"):
                        imdb_id = gid.replace("imdb://", "")

                shows.append({
                    "plex_rating_key": key,
                    "title": show.title,
                    "year": show.year,
                    "tvdb_id": tvdb_id,
                    "imdb_id": imdb_id,
                    "total_size_bytes": total_size,
                    "episode_count": episode_count,
                    "poster_path": getattr(show, "thumb", None),
                    "last_watched_at": last_watched_at,
                    "watched_by": watched_by,
                    "never_watched": len(watched_by) == 0,
                })

        return shows

    def delete_show(self, plex_rating_key: str) -> bool:
        """
        Tell Plex to delete all files for a TV show (uses Plex's own delete API).
        Returns True on success. Requires 'Allow media deletion' in Plex server settings.
        """
        server = self._get_server()
        try:
            show = server.fetchItem(int(plex_rating_key))
            show.delete()
            return True
        except Exception:
            return False
