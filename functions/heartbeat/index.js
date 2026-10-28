// Runs on its schedule (EventBridge Scheduler). Retried twice on failure; then the event is kept in its failed-events queue.
exports.handler = async (event) => {
    console.log(`Scheduled run at ${new Date().toISOString()}: ${JSON.stringify(event)}`);
    return { ok: true };
};
