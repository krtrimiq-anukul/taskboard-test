import { useEffect, useState } from 'react';
import { api } from './api.js';

const COLUMNS = [
  { status: 'todo', label: 'To do' },
  { status: 'doing', label: 'Doing' },
  { status: 'done', label: 'Done' },
];
const ORDER = COLUMNS.map((column) => column.status);

export default function App() {
  const [info, setInfo] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function run(action) {
    setError('');
    setBusy(true);
    try {
      await action();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  const reload = () => run(async () => {
    setInfo(await api.info());
    setTasks(await api.tasks());
  });

  useEffect(() => { reload(); }, []);

  const add = (event) => {
    event.preventDefault();
    if (!title.trim()) return;
    run(async () => {
      const task = await api.create(title.trim());
      setTasks((current) => [...current, task]);
      setTitle('');
    });
  };

  const move = (task, step) => run(async () => {
    const status = ORDER[ORDER.indexOf(task.status) + step];
    const updated = await api.move(task.id, status);
    setTasks((current) => current.map((item) => (item.id === task.id ? updated : item)));
  });

  const remove = (task) => run(async () => {
    await api.remove(task.id);
    setTasks((current) => current.filter((item) => item.id !== task.id));
  });

  const exportAll = () => run(async () => {
    const result = await api.exportTasks();
    setMessage(`Exported to s3://${result.bucket}/${result.key}`);
  });

  return (
    <main className="page">
      <header className="top">
        <div>
          <h1>Taskboard</h1>
          <p className="muted">A small app for testing SDLCForge deployments.</p>
        </div>
        <div className="badges" aria-label="Backend status">
          <span className="badge">version {info?.version ?? '…'}</span>
          <span className="badge">{info?.runtime ?? 'connecting…'}</span>
          <span className={`badge ${info?.database === 'connected' ? 'ok' : 'warn'}`}>database: {info?.database ?? '…'}</span>
          <span className={`badge ${info?.s3_export ? 'ok' : ''}`}>S3 export {info?.s3_export ? 'on' : 'off'}</span>
          <span className={`badge ${info?.sqs_events ? 'ok' : ''}`}>SQS events {info?.sqs_events ? 'on' : 'off'}</span>
        </div>
      </header>

      <form className="add" onSubmit={add}>
        <label htmlFor="title" className="sr-only">New task</label>
        <input id="title" value={title} maxLength={200} placeholder="What needs doing?" onChange={(event) => setTitle(event.target.value)} />
        <button type="submit" disabled={busy || !title.trim()}>Add task</button>
        <button type="button" className="secondary" disabled={busy} onClick={reload}>Refresh</button>
        <button type="button" className="secondary" disabled={busy || !info?.s3_export} onClick={exportAll}
          title={info?.s3_export ? 'Writes every task to the S3 bucket' : 'Needs an S3 bucket bound to the backend'}>Export to S3</button>
      </form>

      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="message">{message}</p>}

      <section className="board">
        {COLUMNS.map((column, index) => (
          <div className="column" key={column.status}>
            <h2>{column.label} <span className="count">{tasks.filter((task) => task.status === column.status).length}</span></h2>
            {tasks.filter((task) => task.status === column.status).map((task) => (
              <article className="task" key={task.id}>
                <p>{task.title}</p>
                <div className="actions">
                  <button type="button" className="secondary" disabled={busy || index === 0} onClick={() => move(task, -1)} aria-label="Move back">←</button>
                  <button type="button" className="secondary" disabled={busy || index === COLUMNS.length - 1} onClick={() => move(task, 1)} aria-label="Move forward">→</button>
                  <button type="button" className="danger" disabled={busy} onClick={() => remove(task)}>Delete</button>
                </div>
              </article>
            ))}
          </div>
        ))}
      </section>
    </main>
  );
}
