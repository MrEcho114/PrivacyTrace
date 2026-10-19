"""Opt-in owned WSL test VM control. This is test infrastructure, never an API.

Only UUID directories below the pre-provisioned task test root are modified.
Runner receives certificate identity only; no database or material-signing key.
"""

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

VM_CONTROL = r"""
import base64,hashlib,json,os,re,signal,socket,subprocess,sys,time
from pathlib import Path
action,nonce,marker=sys.argv[1:]
assert Path('/etc/privacytrace-issue80-test-vm').read_text().strip()==marker,'Wrong test VM'
assert re.fullmatch(r'[a-f0-9-]{36}',nonce)
base=Path('/var/lib/privacytrace-issue80-test/e2e')
base.mkdir(mode=0o700,exist_ok=True)
root=base/nonce
assert root.absolute().is_relative_to(base) and root.resolve()==root.absolute()
data=json.load(sys.stdin)
def write(name,raw):
 p=root/name
 assert p.parent==root
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw)
def free_port():
 with socket.socket() as s:
  s.bind(('127.0.0.1',0));return s.getsockname()[1]
def state():return json.loads((root/'test.json').read_text())
def stop(kind,hard=False):
 p=root/(kind+'.pid')
 if not p.exists():return
 pid=int(p.read_text())
 proc=Path('/proc')/str(pid)
 if not proc.exists():return
 command=(proc/'cmdline').read_bytes()
 if kind=='runner':
  assert b'privacytrace.runner_service' in command
  env=(proc/'environ').read_bytes().split(b'\0')
  assert ('PRIVACYTRACE_RUNNER_ROOT='+str(root/'runner')).encode() in env
  assert not any(b'DATABASE_URL=' in x or b'MATERIAL_KEY' in x for x in env)
 else:
  assert (proc/'cwd').resolve()==root/'redis'
  assert (proc/'exe').resolve()==Path('/usr/bin/redis-server').resolve()
 os.kill(pid,signal.SIGKILL if hard else signal.SIGTERM)
 until=time.monotonic()+10
 while proc.exists() and time.monotonic()<until:
  if ') Z' in (proc/'stat').read_text():break
  time.sleep(.05)
 assert not proc.exists() or ') Z' in (proc/'stat').read_text(),'Owned process did not stop'
 p.unlink(missing_ok=True)
if action=='setup':
 root.mkdir(mode=0o700)
 repo=Path(data['repo'])
 assert repo.is_absolute() and str(repo).startswith('/opt/privacytrace-')
 for name,digest in data['sources'].items():
  assert re.fullmatch(r'[a-z_]+\.py',name)
  observed=hashlib.sha256((repo/'apps/api/src/privacytrace'/name).read_bytes()).hexdigest()
  assert observed==digest,'VM source differs'
 for name in ('ca.pem','runner.pem','runner.key'):
  write(name,base64.b64decode(data['certificates'][name],validate=True))
 redis_port,runner_port=free_port(),free_port()
 (root/'redis').mkdir(mode=0o700)
 username='app_'+data['instance_id'].replace('-','')
 prefix='pt80:'+data['instance_id']+':'
 assert re.fullmatch(r'[a-f0-9]{48}',data['password'])
 assert re.fullmatch(r'[a-f0-9]{48}',data['admin_password'])
 conf=(f'bind 127.0.0.1\nport {redis_port}\nprotected-mode yes\ndir {root}/redis\n'
       f'pidfile {root}/redis.pid\nlogfile {root}/redis.log\n'
       'save ""\nappendonly yes\nappendfsync always\n'
       'maxmemory 64mb\nmaxmemory-policy noeviction\nuser default off\n'
       f"user admin on >{data['admin_password']} ~* &* +@all\n"
       f"user {username} on >{data['password']} ~{prefix}* &{prefix}* "
       '+@read +@write +@connection +@pubsub +@scripting +@transaction '
       '-@admin -@dangerous +eval +evalsha +script|load +client|setname\n')
 write('redis.conf',conf.encode())
 (root/'docker-client').mkdir(mode=0o700)
 env={k:v for k,v in os.environ.items() if not k.startswith('DOCKER_')}
 image=subprocess.check_output(['docker','--host=unix:///var/run/docker.sock','--config',str(root/'docker-client'),'image','inspect','privacytrace-worker:s1','--format={{.Id}}'],env=env,text=True).strip()
 assert re.fullmatch(r'sha256:[a-f0-9]{64}',image)
 saved={'nonce':nonce,'instance_id':data['instance_id'],'repo':str(repo),'image_id':image,'redis_port':redis_port,'runner_port':runner_port}
 write('test.json',json.dumps(saved).encode())
 print(json.dumps(saved))
else:
 saved=state();assert saved['nonce']==nonce
 if action=='configure':
  env={'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8',
       'PYTHONPATH':saved['repo']+'/apps/api/src',
       'PRIVACYTRACE_INSTANCE_ID':saved['instance_id'],'PRIVACYTRACE_RUNNER_IMAGE_ID':saved['image_id'],
       'PRIVACYTRACE_RUNNER_ROOT':str(root/'runner'),'PRIVACYTRACE_RUNNER_BIND':'127.0.0.1',
       'PRIVACYTRACE_RUNNER_PORT':str(saved['runner_port']),'PRIVACYTRACE_RUNNER_TIMEOUT':'120',
       'PRIVACYTRACE_RUNNER_PEERS':data['control_fingerprint'],'PRIVACYTRACE_GATEWAY_URL':data['gateway'],
       'PRIVACYTRACE_RUNNER_TLS_CA':str(root/'ca.pem'),'PRIVACYTRACE_RUNNER_TLS_CERT':str(root/'runner.pem'),'PRIVACYTRACE_RUNNER_TLS_KEY':str(root/'runner.key'),
       'PRIVACYTRACE_RUNNER_GATEWAY_TLS_CA':str(root/'ca.pem'),'PRIVACYTRACE_RUNNER_GATEWAY_TLS_CERT':str(root/'runner.pem'),'PRIVACYTRACE_RUNNER_GATEWAY_TLS_KEY':str(root/'runner.key')}
  write('runner-env.json',json.dumps(env).encode())
 elif action=='redis_start':
  subprocess.run(['redis-server',str(root/'redis.conf'),'--daemonize','yes'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 elif action in ('redis_stop','runner_stop'):
  stop(action.split('_')[0],data.get('hard',False))
 elif action in ('runner_pause','runner_continue'):
  pid=int((root/'runner.pid').read_text());proc=Path('/proc')/str(pid)
  assert b'privacytrace.runner_service' in (proc/'cmdline').read_bytes()
  env=(proc/'environ').read_bytes().split(b'\0')
  assert ('PRIVACYTRACE_RUNNER_ROOT='+str(root/'runner')).encode() in env
  os.kill(pid,signal.SIGSTOP if action=='runner_pause' else signal.SIGCONT)
 elif action=='runner_check':
  p=root/'runner.pid';assert p.exists()
  env=(Path('/proc')/p.read_text().strip()/'environ').read_bytes()
  assert b'DATABASE_URL=' not in env and b'MATERIAL_KEY' not in env
  print(json.dumps({'database_credentials':False,'material_signing_key':False,'docker_host':'local-only'}))
 elif action=='cleanup':
  stop('runner');stop('redis')
  if (root/'runner').exists():
   env=json.loads((root/'runner-env.json').read_text())
   source=("from pathlib import Path;import os;"
    "from privacytrace.runner_service import Runner,RunnerConfig;"
    "from privacytrace.runtime_tls import PrivateClient,RuntimeTLS;"
    "c=RunnerConfig(os.environ['PRIVACYTRACE_INSTANCE_ID'],"
    "os.environ['PRIVACYTRACE_RUNNER_IMAGE_ID'],Path(os.environ['PRIVACYTRACE_RUNNER_ROOT']));"
    "g=PrivateClient(os.environ['PRIVACYTRACE_GATEWAY_URL'],"
    "RuntimeTLS.from_env('PRIVACYTRACE_RUNNER_GATEWAY_TLS'));r=Runner(c,g);r.close()")
   subprocess.run([saved['repo']+'/apps/api/.venv/bin/python','-c',source],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
  import shutil
  assert root.resolve()==base/nonce and state()['nonce']==nonce
  shutil.rmtree(root)
 else:raise AssertionError('Unknown VM test operation')
"""

VM_LAUNCH = r"""
import json,os,sys
from pathlib import Path
root=Path(sys.argv[1]);saved=json.loads((root/'test.json').read_text())
assert root.name==saved['nonce']
assert root.resolve().parent==Path('/var/lib/privacytrace-issue80-test/e2e')
env=json.loads((root/'runner-env.json').read_text())
(root/'runner.pid').write_text(str(os.getpid()))
os.execve(saved['repo']+'/apps/api/.venv/bin/python',[saved['repo']+'/apps/api/.venv/bin/python','-B','-m','privacytrace.runner_service'],env)
"""


class OwnedTestVM:
    def __init__(self, instance_id, tls, control_fingerprint, password, admin_password, repo):
        self.distro = os.environ["PRIVACYTRACE_E2E_WSL_DISTRO"]
        self.marker = os.environ["PRIVACYTRACE_E2E_WSL_MARKER"]
        self.nonce = str(uuid4())
        self.root = "/var/lib/privacytrace-issue80-test/e2e/" + self.nonce
        self.command = ["wsl.exe", "-d", self.distro, "-u", "root", "--exec"]
        self.process = None
        root = Path(__file__).resolve().parents[1] / "src/privacytrace"
        sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("*.py")}
        self.state = self.call(
            "setup",
            instance_id=instance_id,
            password=password,
            admin_password=admin_password,
            repo=repo,
            sources=sources,
            certificates={
                "ca.pem": base64.b64encode(tls.ca.read_bytes()).decode(),
                "runner.pem": base64.b64encode(tls.cert.read_bytes()).decode(),
                "runner.key": base64.b64encode(tls.key.read_bytes()).decode(),
            },
        )
        self.control_fingerprint = control_fingerprint

    def call(self, action, **data):
        result = subprocess.run(
            [*self.command, "python3", "-c", VM_CONTROL, action, self.nonce, self.marker],
            input=json.dumps(data).encode(),
            capture_output=True,
            timeout=60,
        )
        if result.returncode:
            # Never print the private setup payload/config, even on failure.
            raise AssertionError(
                "Owned WSL test operation failed: "
                + action
                + "; "
                + result.stderr.decode(errors="replace")[-1500:]
            )
        return json.loads(result.stdout) if result.stdout.strip() else None

    def configure(self, gateway):
        self.call("configure", gateway=gateway, control_fingerprint=self.control_fingerprint)

    def start_runner(self, log):
        self.process = subprocess.Popen(
            [*self.command, "python3", "-c", VM_LAUNCH, self.root],
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def stop_runner(self, *, hard=False):
        self.call("runner_stop", hard=hard)
        if self.process:
            self.process.wait(timeout=15)

    def close(self):
        self.call("cleanup")
        if self.process:
            self.process.wait(timeout=15)
