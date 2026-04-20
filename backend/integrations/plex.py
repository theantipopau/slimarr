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
