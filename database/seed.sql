UPSERT INTO passengers (id, name, home_region)
VALUES ('maya-chen', 'Maya Chen', 'us-west');

UPSERT INTO agent_memories
  (id, passenger_id, memory_type, content, importance, metadata)
VALUES
  ('mem-red-eye', 'maya-chen', 'PREFERENCE', 'Avoid red-eye departures; an overnight arrival is acceptable but an overnight departure is not.', 0.96, '{"source":"explicit"}'),
  ('mem-window', 'maya-chen', 'PREFERENCE', 'Prefer a window seat whenever one is available.', 0.82, '{"source":"history"}'),
  ('mem-meeting', 'maya-chen', 'TRIP_CONSTRAINT', 'Protect the London meeting before 08:30 BST even when the fare difference is higher.', 1.0, '{"source":"calendar"}'),
  ('mem-recovery-078', 'maya-chen', 'RECOVERY_OUTCOME', 'After a mechanical cancellation and missed connection in March, Maya accepted a more expensive nonstop itinerary because reliability mattered more than price.', 0.89, '{"source":"prior-recovery","case_id":"RR-078"}');
