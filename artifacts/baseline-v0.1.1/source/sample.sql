-- One row per event. The strict left boundary excludes the current event;
-- a timestamp tie excludes both tied events as no ordering is known.
SELECT e.*,
  (SELECT COUNT(*) FROM events h
   WHERE h.user_id=e.user_id AND h.decision_ts < e.decision_ts
     AND h.decision_ts >= e.decision_ts - 86400) AS attempts_24h,
  (SELECT COUNT(*) FROM events h
   WHERE h.user_id=e.user_id AND h.decision_ts < e.decision_ts
     AND h.decision_ts >= e.decision_ts - 604800
     AND h.action='decline' AND h.result_ts <= e.decision_ts) AS declines_7d
FROM events e
ORDER BY e.decision_ts, e.event_id;
