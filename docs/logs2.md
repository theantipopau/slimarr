2026-04-28 01:27:01 | INFO     | backend.core.searcher - Searching for: Mary Poppins (1964)
2026-04-28 01:27:02 | INFO     | backend.core.searcher - Found 132 raw results for Mary Poppins
2026-04-28 01:27:02 | INFO     | backend.core.searcher - Analyzed 132 results: 49 accepted, 83 rejected (68 due to resolution downgrade limit, 12 due to larger size limit).
2026-04-28 01:27:02 | INFO     | backend.core.downloader - Submitted to sabnzbd: Mary.Poppins.1964.1080p.BluRay.x265 → job_id=SABnzbd_nzo_15r1dc3g
2026-04-28 01:27:02 | ERROR    | backend.core.orchestrator - Error processing Mary Poppins: (sqlite3.OperationalError) table downloads has no column named cleanup_status
[SQL: INSERT INTO downloads (movie_id, search_result_id, nzo_id, release_title, expected_size, storage_path, status, progress_pct, error_message, cleanup_status, retry_count, grabbed_at, last_error_at, blacklist_reason, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)]
[parameters: (1608, 197993, 'sabnzbd:SABnzbd_nzo_15r1dc3g', 'Mary.Poppins.1964.1080p.BluRay.x265', 2564152000, None, 'downloading', 0.0, None, 'pending', 0, None, None, None, '2026-04-27 15:27:02.919006', None)]
(Background on this error at: https://sqlalche.me/e/20/e3q8)
2026-04-28 04:00:00 | INFO     | backend.scheduler.scheduler - Orphan scanner triggered
2026-04-28 04:00:00 | ERROR    | backend.core.orphan_scanner - Error scanning SABnzbd orphans: (sqlite3.OperationalError) no such column: downloads.cleanup_status
[SQL: SELECT downloads.id, downloads.movie_id, downloads.search_result_id, downloads.nzo_id, downloads.release_title, downloads.expected_size, downloads.storage_path, downloads.status, downloads.progress_pct, downloads.error_message, downloads.cleanup_status, downloads.retry_count, downloads.grabbed_at, downloads.last_error_at, downloads.blacklist_reason, downloads.started_at, downloads.completed_at 
FROM downloads 
WHERE downloads.nzo_id = ?]
[parameters: ('SABnzbd_nzo_t07_7ael',)]
(Background on this error at: https://sqlalche.me/e/20/e3q8)
2026-04-28 12:41:07 | INFO     | backend.utils.logger - Logger initialised — level=INFO
2026-04-28 12:41:07 | INFO     | backend.scheduler.scheduler - Scheduled nightly cycle at 01:00 UTC
2026-04-28 12:41:07 | INFO     | backend.scheduler.scheduler - Scheduler started
2026-04-28 15:35:06 | INFO     | backend.utils.logger - Logger initialised — level=INFO
2026-04-28 15:35:07 | INFO     | backend.scheduler.scheduler - Scheduled nightly cycle at 01:00 UTC
2026-04-28 15:35:07 | INFO     | backend.scheduler.scheduler - Scheduler started
2026-04-28 15:36:02 | INFO     | backend.core.scanner - Scan started: 1689 movies in Plex
2026-04-28 15:38:41 | INFO     | backend.core.scanner - Scan completed: 1689 movies processed
2026-04-28 19:20:55 | INFO     | backend.core.scanner - Scan started: 1689 movies in Plex
2026-04-28 19:21:36 | INFO     | backend.core.downloader - Submitted to sabnzbd: Roofman.2025.2160p.ATVP.PMTP.WEB-DL.DD.5.1.H.265-PiRaTeS → job_id=SABnzbd_nzo_q0cz_08q
2026-04-28 19:21:48 | INFO     | backend.core.downloader - Download 917: found in sabnzbd history — status='failed' storage='H:\\DOWNLOADS\\USENET\\incomplete\\Roofman.2025.2160p.ATVP.PMTP.WEB-DL.DD.5.1.H.265-PiRaTeS'
2026-04-28 19:21:48 | ERROR    | backend.api.library - Download failed for search result 166854: float() argument must be a string or a real number, not 'NoneType'
2026-04-28 19:22:48 | INFO     | backend.core.downloader - Submitted to sabnzbd: A.Family.Affair.2024.1080p.NF.WEBRip.DDP5.1.x265.10bit-LAMA → job_id=SABnzbd_nzo_fxaw0cj0
2026-04-28 19:23:23 | INFO     | backend.core.scanner - Scan completed: 1689 movies processed
2026-04-28 19:23:56 | INFO     | backend.core.downloader - Download 918: found in sabnzbd history — status='extracting' storage=''
2026-04-28 19:23:56 | ERROR    | backend.api.library - Download failed for search result 82243: float() argument must be a string or a real number, not 'NoneType'
