// Real flow/Vue with a shared rolling HTTP budget; this is a transport model,
// not actual Android acceptance. Native fan-out was measured in issue #133.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const ts = require('typescript')

function laboratory(random = () => 0) {
  let now = 0, sequence = 0, clientNumber = 0
  const scheduled = new Map(), requests = [], cache = new Map()
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports
    const module = { exports: {} }
    cache.set(file, module)
    const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    const context = {
      module, exports: module.exports, crypto: require('node:crypto').webcrypto,
      Math: Object.assign(Object.create(Math), { random }),
      setTimeout(fn, delay) { const id = ++sequence; scheduled.set(id, { fn, at: now + delay }); return id },
      clearTimeout(id) { scheduled.delete(id) },
      require(name) {
        return name.startsWith('.') ? load(path.resolve(path.dirname(file), name + '.ts')) : require(name)
      },
    }
    vm.runInNewContext(code, context, { filename: file })
    return module.exports
  }
  function consume(count) {
    for (let index = 0; index < count; index++) {
      if (requests.filter(at => at > now - 60000).length >= 60) throw 'SERVER_BUSY'
      requests.push(now)
    }
  }
  // The bridge models JSON over HTTP: a read returns a detached copy, never the
  // mutable object the fake server keeps.
  const json = value => JSON.parse(JSON.stringify(value))
  const { createMobileFlow } = load(path.resolve(__dirname, '../src/mobile/flow.ts'))
  function client({ existingJob = true, sources = [], candidates = [] } = {}) {
    const id = (++clientNumber).toString(16).repeat(32)
    const context = { origin: 'https://shared.example/', draft: id, state: 'SERVER_CONFIRMED' }
    const draft = { id, revision: 1, sources, candidates, jobs: existingJob ? [{ job_id: id, events: [] }] : [] }
    const actions = [], saves = [], failures = new Map(), blocked = new Map()
    let job = { id, state: 'QUEUED' }, restores = 0, inFlight = 0, peak = 0
    const bridge = {
      async restore() { restores++; consume(2); return context }, async cancel() {},
      async remove() { return { ...context, state: 'DELETED' } },
      // Native model calls do not consume the HTTP budget the poll shares.
      async modelStatus() { return { configured: false, endpoint: null } },
      async configureModel() { return { configured: true, endpoint: 'https://model.example/v1/chat/completions' } },
      async collect() { return '{"version":"privacytrace-policy-collector/1","results":[]}' },
      async request(action, body) {
        inFlight += 1
        peak = Math.max(peak, inFlight)
        try {
          actions.push({ action, at: now })
          if (blocked.has(action)) { const pending = blocked.get(action); blocked.delete(action); await pending }
          // Yield once so a second concurrent native call would be observed here;
          // the native gate admits exactly one workflow operation at a time.
          await Promise.resolve()
          if (failures.has(action)) { const code = failures.get(action); failures.delete(action); throw code }
          // AnalysisTransport.workflow reconciles capabilities and the draft first.
          consume(action === 'read' ? 2 : 3)
          if (action === 'cancel-job') job = { ...job, state: 'CANCELLED' }
          if (action === 'candidates') {
            // The real save rejects a stale revision before persisting; this fake
            // server does the same so the regression proves the poll refreshed it.
            if (body.revision !== draft.revision) throw 'INPUT_OR_VERSION_REJECTED'
            draft.candidates = body.candidates.map(candidate => ({ ...candidate }))
            draft.revision += 1
            saves.push({ revision: body.revision, candidates: body.candidates.map(candidate => ({ ...candidate })) })
            return { origin: context.origin, draft: context.draft, data: json(draft) }
          }
          const data = action === 'read' ? json(draft) : action === 'taxonomy' ? { data_types: [] } : job
          return { origin: context.origin, draft: context.draft, data }
        } finally {
          inFlight -= 1
        }
      },
    }
    return { flow: createMobileFlow(bridge), actions, id, saves, restores: () => restores,
      peak: () => peak,
      serverCandidates: () => draft.candidates.map(candidate => ({ ...candidate })),
      setJob: state => { job = { ...job, state } },
      bumpRevision: () => { draft.revision += 1 },
      patchCandidate(id, patch) {
        const found = draft.candidates.find(candidate => candidate.id === id)
        if (!found) throw new Error(`no server candidate ${id}`)
        Object.assign(found, patch)
      },
      failNext: (action, code) => failures.set(action, code),
      blockNext(action) {
        let release
        blocked.set(action, new Promise(resolve => { release = resolve }))
        return () => release()
      },
      finish: () => { job = { ...job, state: 'SUCCEEDED' } } }
  }
  async function advance(until) {
    assert.ok(Number.isFinite(until), 'a pending timer must exist')
    while (scheduled.size) {
      const [id, timer] = [...scheduled.entries()].sort((a, b) => a[1].at - b[1].at)[0]
      if (timer.at > until) break
      scheduled.delete(id); now = timer.at
      await timer.fn()
    }
    now = until
  }
  return { client, advance, scheduled, requests, now: () => now,
    next: () => Math.min(...[...scheduled.values()].map(timer => timer.at)) }
}

test('two restored clients sharing 60 HTTP requests/minute leave room for explicit controls', async () => {
  for (const until of [59999, 179999]) {
    const lab = laboratory(), clients = [lab.client(), lab.client()]
    for (const { flow } of clients) await flow.select(true)
    await lab.advance(until)
    for (const { flow, actions, id } of clients) {
      assert.equal(flow.error.value, '', 'shared automatic reads must not consume the full budget')
      assert.equal(flow.job.value.id, id)
      assert.ok(actions.some(item => item.action === 'job' && item.at >= Math.min(120000, until - 30000)), 'keep reading')
      await flow.poll()
      assert.equal(flow.error.value, '')
      await flow.control('cancel-job')
      assert.equal(flow.error.value, '', 'both clients retain budget for cancellation')
      assert.equal(flow.job.value.state, 'CANCELLED')
      assert.equal(actions.filter(item => item.action === 'cancel-job').length, 1)
      assert.equal(actions.filter(item => ['start', 'retry-job'].includes(item.action)).length, 0)
    }
    assert.equal(lab.scheduled.size, 0)
  }
})

test('SERVER_BUSY stays visible, waits at least the current 60s server window, then resumes reads', async () => {
  const lab = laboratory(() => 0.5), { flow, failNext, actions, id } = lab.client()
  await flow.select(true)
  failNext('job', 'SERVER_BUSY')
  await lab.advance(lab.next())
  const failedAt = lab.now(), count = actions.length
  assert.equal(flow.error.value, 'SERVER_BUSY')
  assert.equal(flow.job.value.state, 'QUEUED')
  assert.ok(lab.next() >= failedAt + 60000)
  assert.ok(lab.next() > failedAt + 60000, 'add positive jitter with this seeded sample')
  await lab.advance(failedAt + 59999)
  assert.equal(actions.length, count, 'do not read while backing off')
  await lab.advance(lab.next())
  assert.equal(flow.error.value, '')
  assert.equal(flow.job.value.id, id)
  assert.ok(lab.scheduled.size > 0)
  assert.equal(actions.filter(item => ['start', 'retry-job', 'cancel-job'].includes(item.action)).length, 0)
})

test('repeated busy responses back off with a cap and successful reads reset the delay', async () => {
  const lab = laboratory(), { flow, failNext } = lab.client()
  await flow.select(true)
  for (const minimum of [60000, 120000, 240000, 240000]) {
    failNext('job', 'SERVER_BUSY')
    await lab.advance(lab.next())
    const delay = lab.next() - lab.now()
    assert.ok(delay >= minimum && delay <= 250000)
  }
  await lab.advance(lab.next())
  assert.equal(flow.error.value, '')
  assert.ok(lab.next() - lab.now() < 60000)
  failNext('job', 'SERVER_BUSY')
  await lab.advance(lab.next())
  assert.equal(lab.next() - lab.now(), 60000, 'reset after success')
})

test('a rejected explicit cancel is not replayed automatically or reported as cancelled', async () => {
  const lab = laboratory(), { flow, failNext, actions } = lab.client()
  await flow.select(true)
  failNext('cancel-job', 'SERVER_BUSY')
  await flow.control('cancel-job')
  assert.equal(flow.error.value, 'SERVER_BUSY')
  assert.equal(flow.job.value.state, 'QUEUED')
  await lab.advance(120000)
  assert.equal(flow.job.value.state, 'QUEUED')
  assert.equal(actions.filter(item => item.action === 'cancel-job').length, 1)
})

for (const action of ['stop', 'remove']) {
  test(`${action} during backoff clears pending reads`, async () => {
    const lab = laboratory(), { flow, failNext, actions } = lab.client()
    await flow.select(true)
    failNext('job', 'SERVER_BUSY')
    await lab.advance(lab.next())
    await flow[action]()
    const count = actions.length
    await lab.advance(600000)
    assert.equal(actions.length, count)
    assert.equal(lab.scheduled.size, 0)
  })
}

test('non-busy failures and terminal jobs do not start a retry loop', async () => {
  for (const terminal of [false, true]) {
    const lab = laboratory(), { flow, failNext, finish } = lab.client()
    await flow.select(true)
    if (terminal) finish()
    else failNext('job', 'ACCESS_REJECTED')
    await lab.advance(lab.next())
    assert.equal(lab.scheduled.size, 0)
    assert.equal(flow.error.value, terminal ? '' : 'ACCESS_REJECTED')
  }
})

test('a stale in-flight read cannot clear the new generation polling timer', async () => {
  const lab = laboratory(), { flow, blockNext } = lab.client()
  await flow.select(true)
  const release = blockNext('job'), pending = flow.poll()
  await flow.stop()
  await flow.select(true)
  assert.equal(lab.scheduled.size, 1)
  release(); await pending
  assert.equal(lab.scheduled.size, 1, 'stale completion must leave the new timer intact')
  assert.equal(flow.error.value, '')
})

for (const action of ['read', 'taxonomy', 'job']) {
  test(`a busy ${action} while restoring keeps the failure visible and resumes without another restore`, async () => {
    const lab = laboratory(), { flow, failNext, id, actions, restores } = lab.client()
    failNext(action, 'SERVER_BUSY')
    await flow.select(true)
    assert.equal(flow.error.value, 'SERVER_BUSY')
    assert.equal(flow.job.value, null, 'do not invent a job state')
    assert.ok(Number.isFinite(lab.next()) && lab.next() >= 60000)
    await lab.advance(lab.next())
    assert.equal(flow.error.value, '')
    assert.equal(flow.job.value.id, id)
    assert.equal(restores(), 1, 'automatic recovery must not reopen native restore/confirmation')
    assert.equal(actions.filter(item => ['start', 'retry-job', 'cancel-job'].includes(item.action)).length, 0)
  })
}

test('busy recovery for saved materials without a job never starts an analysis', async () => {
  const lab = laboratory(), { flow, failNext, actions } = lab.client({ existingJob: false })
  failNext('taxonomy', 'SERVER_BUSY')
  await flow.select(true)
  await lab.advance(lab.next())
  assert.equal(flow.error.value, '')
  assert.equal(flow.job.value, null)
  assert.equal(lab.scheduled.size, 0)
  assert.equal(actions.filter(item => ['job', 'start', 'retry-job'].includes(item.action)).length, 0)
})

test('automatic polling issues one native workflow call at a time', async () => {
  const lab = laboratory(), { flow, peak } = lab.client()
  await flow.select(true)
  await lab.advance(lab.next())
  assert.equal(flow.error.value, '')
  assert.equal(peak(), 1, 'the native gate admits a single workflow operation')
  await lab.advance(lab.next())
  assert.equal(peak(), 1, 'every automatic read stays sequential')
})

test('a transient native busy retries quickly instead of stopping the progress loop', async () => {
  const lab = laboratory(), { flow, failNext, id } = lab.client()
  await flow.select(true)
  failNext('job', 'BUSY_OR_INACTIVE')
  await lab.advance(lab.next())
  assert.equal(flow.error.value, '', 'a transient native busy is not surfaced')
  const retryAt = lab.next()
  assert.ok(Number.isFinite(retryAt), 'a retry timer must exist')
  assert.ok(retryAt - lab.now() <= 2000, 'retry quickly rather than waiting for a user refresh')
  await lab.advance(retryAt)
  assert.equal(flow.error.value, '')
  assert.equal(flow.job.value.id, id)
  assert.ok(lab.scheduled.size > 0, 'polling continues after the transient busy')
})

test('persistent native busy stays bounded, visible and does not loop forever', async () => {
  const lab = laboratory(), { flow, failNext } = lab.client()
  await flow.select(true)
  for (let attempt = 0; attempt < 4; attempt++) {
    failNext('job', 'BUSY_OR_INACTIVE')
    await lab.advance(lab.next())
  }
  assert.equal(flow.error.value, 'BUSY_OR_INACTIVE')
  assert.equal(lab.scheduled.size, 0, 'no unbounded retry loop once the bounded retries are spent')
})

// #239: a successful foreground read or model settings update must hand the
// running job back to the automatic poll instead of leaving the progress page on
// a stale stage until the user presses "刷新进度" by hand.
test('a successful foreground read or model settings update resumes polling', async () => {
  for (const action of ['refresh', 'settings']) {
    const lab = laboratory(), { flow, actions, id, peak } = lab.client()
    await flow.select(true)
    assert.equal(lab.scheduled.size, 1, 'restore leaves exactly one automatic poll')
    await flow[action](true)
    assert.equal(flow.error.value, '')
    assert.equal(lab.scheduled.size, 1, `${action} must leave exactly one timer instead of stopping the loop`)
    const reads = actions.filter(item => item.action === 'job').length
    await lab.advance(lab.next())
    assert.equal(actions.filter(item => item.action === 'job').length, reads + 1, `${action} must resume automatic job reads`)
    assert.equal(flow.error.value, '')
    assert.equal(flow.job.value.id, id)
    assert.equal(peak(), 1, 'resumed reads stay sequential through the native gate')
  }
})

test('stop, delete and a terminal job never revive automatic polling', async () => {
  const lab = laboratory(), { flow, finish } = lab.client()
  await flow.select(true)
  await flow.stop()
  assert.equal(lab.scheduled.size, 0, 'stop clears the pending poll')
  await flow.remove()
  assert.equal(flow.job.value, null)
  assert.equal(lab.scheduled.size, 0, 'deleting the material leaves nothing to poll')
  await flow.refresh()
  assert.equal(lab.scheduled.size, 0, 'a reload without a job must not invent a poll')
  const second = laboratory(), rest = second.client()
  await rest.flow.select(true)
  rest.finish()
  await second.advance(second.next())
  assert.equal(rest.flow.job.value.state, 'SUCCEEDED')
  assert.equal(second.scheduled.size, 0, 'a terminal job ends the poll loop')
  await rest.flow.refresh()
  assert.equal(second.scheduled.size, 0, 'a foreground action must not revive a finished job')
})

test('a late automatic read cannot add a second timer after a foreground action', async () => {
  const lab = laboratory(), { flow, blockNext } = lab.client()
  await flow.select(true)
  const release = blockNext('job'), pending = flow.poll(true)
  await flow.refresh()
  assert.equal(lab.scheduled.size, 1, 'the foreground action owns the only pending timer')
  release(); await pending
  assert.equal(lab.scheduled.size, 1, 'the superseded read must leave the new timer alone')
})

// #273: the candidate page stays editable while the progress poll runs. A
// background read must refresh the job stage and draft revision but never replace
// inputs, checked state or a locally added candidate the user has not saved yet.
test('a background poll keeps unsaved candidate edits and the refreshed revision saves them', async () => {
  const seeded = {
    sources: [{
      id: 's1', title: '官网政策', source_type: 'OFFICIAL_WEB_POLICY', url: 'https://example.com/privacy',
      text: '我们会收集位置信息用于提供服务。我们不会出售个人信息。', status: 'ready', version: '2026-01',
    }],
    candidates: [
      { id: 'c1', source_id: 's1', excerpt: '我们会收集位置信息', data_type: 'LOCATION', checked: false, declared_purpose: null },
      { id: 'c2', source_id: 's1', excerpt: '我们不会出售个人信息', data_type: 'PERSONAL_INFO', checked: false, declared_purpose: null },
    ],
  }
  const lab = laboratory(), client = lab.client(seeded)
  const { flow, actions, saves, setJob, bumpRevision, patchCandidate } = client
  await flow.select(true)
  // The step rail returns to candidates without another read, as in the report:
  // the job keeps running and the candidate editor is not busy.
  flow.state.step = 'candidates'
  assert.equal(flow.state.candidates.map(candidate => candidate.id).join(','), 'c1,c2')

  const edited = flow.state.candidates.find(candidate => candidate.id === 'c2')
  edited.purpose = '用户尚未保存的目的'
  flow.state.candidates.push({ id: 'local-1', sourceId: 's1', quote: '我们不会出售个人信息', dataType: 'PERSONAL_INFO',
    polarity: 'UNKNOWN', subject: 'UNKNOWN', condition: '', checked: false, action: 'UNKNOWN' })
  const savesBefore = saves.length

  // The job advances, another writer changes c1, and the draft revision moves on.
  setJob('INTAKE')
  patchCandidate('c1', { checked: true, declared_purpose: '服务端写入目的' })
  bumpRevision()
  await lab.advance(lab.next())

  assert.equal(flow.error.value, '')
  assert.equal(flow.job.value.state, 'INTAKE', 'the job stage still updates')
  assert.equal(flow.draft.value.revision, 2, 'the poll still applies the newer server revision')
  assert.equal(flow.state.candidates.map(candidate => candidate.id).join(','), 'c1,c2,local-1', 'local order and additions survive')
  assert.equal(flow.state.candidates.find(candidate => candidate.id === 'c2').purpose, '用户尚未保存的目的', 'unsaved input survives the poll')
  assert.equal(flow.state.candidates.find(candidate => candidate.id === 'c2').checked, false, 'an unsaved candidate is never shown as checked')
  assert.equal(flow.state.candidates.find(candidate => candidate.id === 'c1').checked, true, 'untouched candidates still follow the server')
  assert.equal(flow.state.candidates.find(candidate => candidate.id === 'c1').purpose, '服务端写入目的')
  assert.equal(saves.length, savesBefore, 'an automatic poll never saves candidates')
  assert.equal(actions.filter(action => action.action === 'candidates').length, 0)
  assert.equal(client.serverCandidates().find(candidate => candidate.id === 'c2').declared_purpose, null, 'the edit stays local until the explicit save')

  // A second poll (25s later) keeps the same local edit and the new stage.
  setJob('POLICY_PARSING')
  bumpRevision()
  await lab.advance(lab.next())
  assert.equal(flow.job.value.state, 'POLICY_PARSING')
  assert.equal(flow.draft.value.revision, 3)
  assert.equal(flow.state.candidates.find(candidate => candidate.id === 'c2').purpose, '用户尚未保存的目的')

  // The explicit save succeeds because the polls kept the draft revision fresh;
  // the fake server rejects a stale revision just like the real endpoint.
  await flow.save()
  assert.equal(flow.error.value, '')
  assert.equal(saves.length, 1)
  assert.equal(saves[0].revision, 3)
  assert.equal(saves[0].candidates.find(candidate => candidate.id === 'c2').declared_purpose, '用户尚未保存的目的')
  assert.equal(saves[0].candidates.find(candidate => candidate.id === 'c1').checked, true)
  assert.equal(saves[0].candidates.length, 3, 'the locally added candidate is saved explicitly, not by polling')
  assert.equal(flow.draft.value.revision, 4, 'the save response is applied')
  assert.equal(flow.state.candidates.find(candidate => candidate.id === 'c2').purpose, '用户尚未保存的目的')
  assert.equal(flow.state.candidates.find(candidate => candidate.id === 'c2').checked, false)
})
