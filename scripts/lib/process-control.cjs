// Process control shared by the acceptance harnesses.
//
// Both scripts start their servers with `shell: true`, so the real server is a
// grandchild of the shell. Terminating only the direct PID would leave the
// server holding the temp store and its port bound, so every helper here works
// on the whole tree.

const { execSync } = require('child_process');

// True while the OS still knows about this PID. Signal 0 performs the existence
// and permission checks without delivering a signal, so it is the authoritative
// liveness probe -- a child's exitCode only reflects the direct process and
// misses a server the shell left behind.
function isProcessAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    // EPERM means the process exists but belongs to another user.
    return err.code === 'EPERM';
  }
}

// Terminates a process tree this script spawned; never an unknown PID.
function killProcessTree(pid) {
  if (!pid) return;
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
      return;
    }
    // POSIX: the child was started detached, so it leads its own process group
    // and a negative PID signals the shell and the server together.
    process.kill(-pid, 'SIGKILL');
  } catch {
    // The group may already be gone while the direct child survives, or the
    // group was never created. Fall back to the single process.
    try {
      process.kill(pid, 'SIGKILL');
    } catch {
      // Already dead; nothing to do.
    }
  }
}

// Terminates the spawned children and waits until the OS confirms they are
// gone, so a temp store is never removed while a server still holds files
// inside it. Returns the survivors instead of pretending the kill worked.
async function stopChildren(children, timeoutMs = 10000) {
  for (const child of children) {
    killProcessTree(child.pid);
  }
  const alive = () => children.filter(child => isProcessAlive(child.pid));
  const deadline = Date.now() + timeoutMs;
  let survivors = alive();
  while (survivors.length > 0 && Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 100));
    survivors = alive();
  }
  if (survivors.length > 0) {
    // One last escalation before reporting, so a slow shutdown gets a chance.
    for (const child of survivors) killProcessTree(child.pid);
    await new Promise(r => setTimeout(r, 500));
    survivors = alive();
  }
  return survivors;
}

// Spawn options shared by every server these scripts start.
//
// `shell: true` is required so `uv`/`npm` resolve their shims, which means the
// real server is a grandchild of the shell. On POSIX the child is started
// detached so it leads its own process group, which is what makes the
// negative-PID kill reach the server as well as the shell. Windows uses
// `taskkill /T`, which walks the tree on its own, so it must NOT be detached.
function spawnOptions(cwd, env) {
  return {
    cwd,
    shell: true,
    stdio: 'pipe',
    env: { ...process.env, ...env },
    ...(process.platform === 'win32' ? {} : { detached: true }),
  };
}

module.exports = { isProcessAlive, killProcessTree, stopChildren, spawnOptions };
