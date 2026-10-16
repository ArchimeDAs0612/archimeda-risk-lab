-- Half-open history; equal-time events are excluded, all inputs known by decision.
SELECT
  e.event_id,
  (SELECT COUNT(*) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-3600 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_attempts_1h,
  (SELECT COALESCE(SUM(h.amount),0) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-3600 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_amount_1h,
  (SELECT COUNT(*) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-86400 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_attempts_24h,
  (SELECT COALESCE(SUM(h.amount),0) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-86400 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_amount_24h,
  (SELECT COUNT(*) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-604800 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_attempts_7d,
  (SELECT COALESCE(SUM(h.amount),0) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-604800 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_amount_7d,
  (SELECT COUNT(DISTINCT h.linked_device_id) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-604800 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_devices_7d,
  (SELECT COUNT(DISTINCT h.payment_tool_id) FROM events h WHERE h.user_id=e.user_id AND h.decision_ts>=e.decision_ts-604800 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS user_tools_7d,
  (SELECT COUNT(DISTINCT h.user_id) FROM events h WHERE h.linked_device_id=e.linked_device_id AND h.decision_ts>=e.decision_ts-604800 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS device_users_7d,
  (SELECT COUNT(DISTINCT h.user_id) FROM events h WHERE h.payment_tool_id=e.payment_tool_id AND h.decision_ts>=e.decision_ts-604800 AND h.decision_ts<e.decision_ts AND h.available_ts<=e.decision_ts) AS tool_users_7d
FROM events e ORDER BY e.decision_ts,e.event_id;
