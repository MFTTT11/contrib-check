import React, { useEffect, useState } from 'react';
import ForgeReconciler, { Heading, Link, Lozenge, Spinner, Stack, Text } from '@forge/react';
import { invoke } from '@forge/bridge';

const LOOK = { clear: ['success', 'No overlap found'], check: ['moved', 'Check before starting'], unknown: ['default', 'Could not check'] };

const App = () => {
  const [report, setReport] = useState(null);
  useEffect(() => { invoke('getReport').then(setReport).catch(() => setReport({ status: 'unknown', reasons: ['The check failed'], similar: [], github: [] })); }, []);
  if (!report) return <Spinner label="Checking for overlapping work" />;
  const [appearance, label] = LOOK[report.status] || LOOK.unknown;
  return (
    <Stack space="space.100">
      <Lozenge appearance={appearance}>{label}</Lozenge>
      {report.reasons.map((r) => <Text key={r}>{r}</Text>)}
      {report.similar.length > 0 && <Heading as="h4">Similar open issues</Heading>}
      {report.similar.map((s) => (
        <Text key={s.key}><Link href={`/browse/${s.key}`}>{s.key}</Link> {s.summary} ({s.status}{s.assignee ? `, ${s.assignee}` : ''})</Text>
      ))}
      {report.github.filter((g) => !g.error && !g.competing?.length && !g.assignees?.length).map((g) => (
        <Text key={g.url}><Link href={g.url}>{g.url}</Link>: open, unassigned, no competing PRs</Text>
      ))}
    </Stack>
  );
};

ForgeReconciler.render(<React.StrictMode><App /></React.StrictMode>);
