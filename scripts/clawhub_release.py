#!/usr/bin/env python3
"""Fail-closed ZenStory ClawHub release controller (standard library only)."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA=1; CLI_VERSION="0.23.3"; REGISTRY="https://clawhub.ai"
SEMVER=re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
SHA=re.compile(r"^[0-9a-f]{40}$"); REPO=re.compile(r"^zenstory-ai/[\w.-]+$")
SLUG=re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"); OWNER=re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
SKILL_DEP=re.compile(r"^skill:([A-Za-z0-9][A-Za-z0-9-]{0,38})/([a-z0-9]+(?:-[a-z0-9]+)*)@(.+)$")
CATEGORIES={"integrations","automation","research","development","productivity","communication","creative","knowledge","agents","operations","security","finance","lifestyle","other"}
FIELDS={"path","slug","publisher","version","displayName","disposition","excludeReason","maintainer","include","rebuildOn","runtimeDependsOn","supportedRuntimes","rights"}
SECRET_NAMES={".env",".npmrc",".pypirc","id_rsa","id_ed25519","credentials.json","service-account.json","secrets.json"}

class PolicyError(RuntimeError): pass
class RemoteError(RuntimeError): pass

def digest(data:bytes)->str: return hashlib.sha256(data).hexdigest()
def canonical(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def read(path:Path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e: raise PolicyError(f"cannot read JSON {path}: {e}") from e
def write(path:Path,x):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(x,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
def rel(value,where):
    if not isinstance(value,str) or not value or "\\" in value or "\0" in value: raise PolicyError(f"{where} must be a POSIX relative path")
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in ("",".","..") for x in p.parts): raise PolicyError(f"{where} escapes allowed root: {value!r}")
    return p
def require(obj,keys,where):
    missing=sorted(keys-set(obj))
    if missing: raise PolicyError(f"{where} missing fields: {', '.join(missing)}")
def git_head(root):
    p=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],text=True,capture_output=True)
    return p.stdout.strip() if p.returncode==0 and SHA.fullmatch(p.stdout.strip()) else None

def validate_manifest(m,root:Path):
    if not isinstance(m,dict): raise PolicyError("manifest must be an object")
    require(m,{"schemaVersion","repository","skillRoots","bootstrapSha","skills"},"manifest")
    if m["schemaVersion"]!=SCHEMA: raise PolicyError("schemaVersion must be 1")
    if not isinstance(m["repository"],str) or not REPO.fullmatch(m["repository"]): raise PolicyError("invalid repository")
    if not isinstance(m["bootstrapSha"],str) or not SHA.fullmatch(m["bootstrapSha"]): raise PolicyError("bootstrapSha must be a full lowercase SHA")
    if not isinstance(m["skillRoots"],list) or not m["skillRoots"]: raise PolicyError("skillRoots must be non-empty")
    roots=[rel(x,"skillRoots[]") for x in m["skillRoots"]]
    if not isinstance(m["skills"],list): raise PolicyError("skills must be a list")
    paths=set(); ids=set()
    for i,s in enumerate(m["skills"]):
        w=f"skills[{i}]"
        if not isinstance(s,dict): raise PolicyError(f"{w} must be an object")
        require(s,FIELDS,w); p=rel(s["path"],w+".path"); ps=p.as_posix()
        if ps in paths: raise PolicyError(f"duplicate path {ps}")
        paths.add(ps)
        if not any(p==r or r in p.parents for r in roots): raise PolicyError(f"{w}.path outside skillRoots")
        d=root/ps
        cursor=root
        for part in p.parts:
            cursor=cursor/part
            if cursor.is_symlink(): raise PolicyError(f"{ps} traverses symlink component {cursor}")
        if not (d/"SKILL.md").is_file(): raise PolicyError(f"{ps} must be a real directory containing SKILL.md")
        if not isinstance(s["slug"],str) or not SLUG.fullmatch(s["slug"]): raise PolicyError(f"{w}.slug invalid")
        if not isinstance(s["publisher"],str) or not OWNER.fullmatch(s["publisher"]): raise PolicyError(f"{w}.publisher invalid")
        ident=(s["publisher"].lower(),s["slug"])
        if ident in ids: raise PolicyError(f"duplicate identity {s['publisher']}/{s['slug']}")
        ids.add(ident)
        if s["disposition"] not in {"publish","excluded","blocked"}: raise PolicyError(f"{w}.disposition invalid")
        if not isinstance(s["excludeReason"],str) or (s["disposition"]!="publish" and not s["excludeReason"].strip()): raise PolicyError(f"{w}.excludeReason required")
        if s["disposition"]=="publish" and s["excludeReason"]: raise PolicyError(f"{w}.excludeReason must be empty")
        if not isinstance(s["version"],str) or not SEMVER.fullmatch(s["version"]): raise PolicyError(f"{w}.version must be semver")
        if not isinstance(s["displayName"],str) or not s["displayName"].strip() or not isinstance(s["maintainer"],str) or not s["maintainer"].strip(): raise PolicyError(f"{w} displayName/maintainer required")
        for f in ("include","rebuildOn","runtimeDependsOn","supportedRuntimes"):
            if not isinstance(s[f],list) or any(not isinstance(x,str) or not x for x in s[f]): raise PolicyError(f"{w}.{f} must be a string list")
        if s["disposition"]=="publish" and not s["include"]: raise PolicyError(f"{w}.include cannot be empty")
        for dep in s["runtimeDependsOn"]:
            if dep.startswith("skill:"):
                match=SKILL_DEP.fullmatch(dep)
                if not match or not SEMVER.fullmatch(match.group(3)): raise PolicyError(f"{w} skill dependency must be skill:owner/slug@semver")
                if s["disposition"]=="publish" and match.group(1).lower()!=s["publisher"].lower(): raise PolicyError(f"{w} cross-owner companion layout is unsupported without an adapter")
        for x in s["include"]: rel(x,w+".include[]")
        cats=s.get("categories",[]); topics=s.get("topics",[])
        if not isinstance(cats,list) or len(cats)>3 or len(set(cats))!=len(cats) or any(x not in CATEGORIES for x in cats): raise PolicyError(f"{w}.categories invalid")
        if not isinstance(topics,list) or len(topics)>5 or len(set(topics))!=len(topics) or any(not isinstance(x,str) or not x or len(x)>48 for x in topics): raise PolicyError(f"{w}.topics invalid")
        if "catalogMigration" in s and not isinstance(s["catalogMigration"],bool): raise PolicyError(f"{w}.catalogMigration must be boolean")
        rights=s["rights"]
        if not isinstance(rights,dict) or rights.get("status") not in {"self-authored","permission-recorded","unconfirmed"} or not isinstance(rights.get("evidence"),str) or not rights["evidence"].strip(): raise PolicyError(f"{w}.rights invalid")
        if s["disposition"]=="publish" and rights["status"]=="unconfirmed": raise PolicyError(f"{w} cannot publish with unconfirmed MIT-0 rights")
    found=set()
    for r in roots:
        rd=root/r.as_posix()
        if not rd.is_dir(): raise PolicyError(f"missing skill root {r}")
        for marker in rd.rglob("SKILL.md"):
            if marker.is_symlink(): raise PolicyError(f"symlink marker {marker}")
            found.add(marker.parent.relative_to(root).as_posix())
    if found-paths: raise PolicyError("unclassified skill directories: "+", ".join(sorted(found-paths)))
    if paths-found: raise PolicyError("declared skill directories missing SKILL.md: "+", ".join(sorted(paths-found)))
    for i,s in enumerate(m["skills"]):
        if s["disposition"]=="publish":
            expected=s.get("packageDigest")
            if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{64}",expected): raise PolicyError(f"skills[{i}].packageDigest must lock the publish inventory")
            actual=inventory_digest(package(root,s))
            if actual!=expected: raise PolicyError(f"skills[{i}].packageDigest does not match packaged source; bump version and run lock")

def secret(p:PurePosixPath):
    parts=[x.lower() for x in p.parts]; n=parts[-1]
    return n in SECRET_NAMES or n in {"token","token.json","auth-token","access-token"} or n.endswith((".pem",".p12",".pfx",".key",".keystore")) or any(x in {".git",".ssh","private","secrets"} for x in parts)
def package(root:Path,s):
    base=root/rel(s["path"],"skill.path").as_posix(); resolved_base=base.resolve(strict=True); selected={}
    for pat in s["include"]:
        rel(pat,"skill.include[]")
        for f in base.glob(pat):
            if f.is_dir(): continue
            p=PurePosixPath(f.relative_to(base).as_posix())
            if secret(p): raise PolicyError(f"unsafe publish file {s['path']}/{p}")
            if any(part.startswith(".") for part in p.parts) or "node_modules" in p.parts:
                continue
            cursor=base
            for part in p.parts:
                cursor=cursor/part
                if cursor.is_symlink(): raise PolicyError(f"unsafe symlink component {s['path']}/{p}")
            try: resolved=f.resolve(strict=True)
            except OSError as e: raise PolicyError(f"cannot resolve publish file {s['path']}/{p}: {e}") from e
            if not resolved.is_relative_to(resolved_base): raise PolicyError(f"unsafe publish file {s['path']}/{p}")
            selected[p.as_posix()]=f
    if "SKILL.md" not in selected: raise PolicyError(f"{s['path']} include omits SKILL.md")
    if not any(PurePosixPath(x).name.lower().startswith("license") for x in selected):
        ls=sorted(x for x in root.glob("LICENSE*") if x.is_file() and not x.is_symlink())
        if ls: selected[ls[0].name]=ls[0]
    deps=[x for x in s["runtimeDependsOn"] if x.startswith("skill:")]
    if deps:
        body="# Exact companion skills\n\nClawHub does not auto-install these dependencies. Install all into the same skills root:\n\n```sh\n"+"\n".join(f"clawhub install @{SKILL_DEP.fullmatch(x).group(1)}/{SKILL_DEP.fullmatch(x).group(2)} --version {SKILL_DEP.fullmatch(x).group(3)}" for x in deps)+"\n```\n"
        selected["INSTALL.md"]=body.encode()
    out=[]
    for p,f in sorted(selected.items()):
        b=f if isinstance(f,bytes) else f.read_bytes(); out.append({"path":p,"source":None if isinstance(f,bytes) else f,"bytes":b if isinstance(f,bytes) else None,"size":len(b),"sha256":digest(b)})
    return out
def fingerprint(files):
    # clawhub@0.23.3 uses JavaScript path.localeCompare(), not byte ordering.
    # ZenStory package paths are ASCII; casefold ordering matches the CLI's ICU
    # ordering for this allowed set. Every real plan additionally compares this
    # result with the pinned CLI's dry-run fingerprint and fails on divergence.
    rows=[(x["path"],x["sha256"]) for x in files]
    return digest("\n".join(f"{p}:{h}" for p,h in sorted(rows,key=lambda x:x[0].casefold())).encode())
def inventory_digest(files):
    rows=sorted(({"path":x["path"],"sha256":x["sha256"],"size":x["size"]} for x in files),key=lambda x:x["path"])
    return digest(canonical(rows))
def stage(files,target):
    for x in files:
        d=target/x["path"]; d.parent.mkdir(parents=True,exist_ok=True)
        if x.get("bytes") is not None:d.write_bytes(x["bytes"])
        else:shutil.copyfile(x["source"],d)

class Registry:
    def __init__(self,base=None): self.base=(base or os.getenv("CLAWHUB_REGISTRY_URL") or REGISTRY).rstrip("/")
    def get(self,path,q):
        req=Request(self.base+path+"?"+urlencode(q),headers={"Accept":"application/json","User-Agent":"zenstory-clawhub-controller/1"})
        try:
            with urlopen(req,timeout=20) as r:return json.loads(r.read().decode())
        except HTTPError as e:
            if e.code==404:return None
            raise RemoteError(f"HTTP {e.code} from ClawHub") from e
        except (URLError,TimeoutError,json.JSONDecodeError) as e: raise RemoteError(f"ClawHub read failed: {e}") from e
    def resolve(self,p,s,h): return self.get("/api/v1/resolve",{"slug":s,"ownerHandle":p,"hash":h})
    def skill(self,p,s): return self.get(f"/api/v1/skills/{s}",{"ownerHandle":p})
    def version(self,p,s,v): return self.get(f"/api/v1/skills/{s}/versions/{v}",{"ownerHandle":p})
    def scan(self,p,s,v): return self.get(f"/api/v1/skills/{s}/scan",{"ownerHandle":p,"version":v})
def owner(meta):
    if not meta:return None
    x=meta.get("owner") or meta.get("publisher")
    return (x.get("handle") or x.get("slug")) if isinstance(x,dict) else meta.get("ownerHandle") or (x if isinstance(x,str) else None)
def remote_inventory(data):
    x=data.get("version",data) if isinstance(data,dict) else {}; fs=x.get("files") if isinstance(x,dict) else None
    if not isinstance(fs,list):return None,[]
    normal=[]; generated=[]
    for f in fs:
        if not isinstance(f,dict) or not isinstance(f.get("path"),str) or not isinstance(f.get("sha256"),str):return None,[]
        if f["path"]=="skill-card.md":generated.append(f["path"])
        else:normal.append(f)
    return fingerprint(normal),generated
def remote_package_digest(data):
    x=data.get("version",data) if isinstance(data,dict) else {};fs=x.get("files") if isinstance(x,dict) else None
    if not isinstance(fs,list):return None
    normal=[]
    for f in fs:
        if not isinstance(f,dict) or not all(k in f for k in ("path","sha256","size")):return None
        if f["path"]!="skill-card.md":normal.append(f)
    return inventory_digest(normal)
def metadata_diff(meta,s):
    if meta is None:return [x for x in ("displayName","categories","topics") if s.get(x)]
    skill=meta.get("skill",meta); catalog=meta.get("metadata",{}) if isinstance(meta.get("metadata",{}),dict) else {}; out=[]
    if skill.get("displayName") is not None and skill["displayName"]!=s["displayName"]:out.append("displayName")
    for k in ("categories","topics"):
        observed=skill.get(k) if skill.get(k) is not None else catalog.get(k)
        if observed is not None:
            obs=[z.get("slug") if isinstance(z,dict) else z for z in observed]
            if sorted(obs)!=sorted(s.get(k,[])):out.append(k)
    return out
def metadata_unobserved(meta,s):
    if meta is None:return []
    skill=meta.get("skill",meta);catalog=meta.get("metadata",{}) if isinstance(meta.get("metadata",{}),dict) else {}
    return [k for k in ("categories","topics") if s.get(k) and k not in skill and k not in catalog]
def dependency_state(reg,s):
    evidence=[]
    for value in s["runtimeDependsOn"]:
        if not value.startswith("skill:"):continue
        match=SKILL_DEP.fullmatch(value);p,slug,v=match.groups();vd=reg.version(p,slug,v);scan=reg.scan(p,slug,v)
        sec=scan.get("security",{}) if isinstance(scan,dict) else {}
        status="verified" if vd and sec.get("status")=="clean" and sec.get("hasScanResult") is True else "unverified"
        evidence.append({"identity":f"{p}/{slug}","version":v,"status":status})
    return evidence
def inspect(reg,s,fp):
    p,slug,v=s["publisher"],s["slug"],s["version"]; res=reg.resolve(p,slug,fp); meta=reg.skill(p,slug)
    if owner(meta) and owner(meta).lower()!=p.lower():return {"status":"OWNER_MISMATCH","observedOwner":owner(meta)}
    vd=reg.version(p,slug,v); md=metadata_diff(meta,s)
    if vd:
        _,gen=remote_inventory(vd);actual_package=remote_package_digest(vd);expected_package=s.get("packageDigest")
        if actual_package is None:return {"status":"UNKNOWN","reason":"remote file hashes/sizes unavailable"}
        if actual_package!=expected_package:return {"status":"CONTENT_CONFLICT","actualPackageDigest":actual_package,"expectedPackageDigest":expected_package,"serverGeneratedFiles":gen}
        if md:return {"status":"POLICY_DRIFT","metadataDifferences":md,"packageDigest":actual_package,"serverGeneratedFiles":gen}
        scan=reg.scan(p,slug,v); sec=scan.get("security",{}) if isinstance(scan,dict) else {}
        evidence={k:sec.get(k) for k in ("status","hasScanResult","hasWarnings")}
        if sec.get("status")=="clean" and sec.get("hasScanResult") is True:
            deps=dependency_state(reg,s)
            if any(x["status"]!="verified" for x in deps):return {"status":"BLOCKED_DEPENDENCY","packageDigest":actual_package,"dependencies":deps,"security":evidence}
            status="DEPENDENCY_PUBLIC_VERIFIED" if deps else "DISTRIBUTION_VERIFIED"
            return {"status":status,"packageDigest":actual_package,"serverGeneratedFiles":gen,"security":evidence,"dependencies":deps,"metadataUnobserved":metadata_unobserved(meta,s)}
        if sec.get("status") in {"pending","queued","scanning"}:return {"status":"PENDING_REVIEW","security":evidence}
        if sec.get("status") in {"blocked","malicious","rejected"}:return {"status":"BLOCKED_MODERATION","security":evidence}
        return {"status":"UNKNOWN","reason":"aggregate scan not clean/complete","security":evidence}
    if res and res.get("match"):return {"status":"CONTENT_AT_OTHER_VERSION","match":res["match"],"latestVersion":res.get("latestVersion")}
    latest=res.get("latestVersion") if res else None
    latest_value=latest.get("version") if isinstance(latest,dict) else latest
    def core(v):
        m=SEMVER.fullmatch(v or "");return tuple(map(int,m.groups()[:3])) if m else None
    if core(latest_value) and core(latest_value)>core(v):return {"status":"REMOTE_AHEAD","latestVersion":latest_value,"desiredVersion":v}
    return {"status":"MISSING","latestVersion":latest,"metadataDifferences":md}

def check_cli(bin):
    p=subprocess.run([bin,"--cli-version"],text=True,capture_output=True); text=(p.stdout+p.stderr).strip()
    if p.returncode or text!=CLI_VERSION:raise PolicyError(f"clawhub must be exactly {CLI_VERSION}; got {text or 'unavailable'}")
def cli(bin,args,expected,retries=3):
    for n in range(retries):
        p=subprocess.run([bin,*args],text=True,capture_output=True); text=p.stdout+"\n"+p.stderr; parsed=None
        try:parsed=json.loads(p.stdout.strip())
        except json.JSONDecodeError:
            for line in reversed(p.stdout.splitlines()):
                try:parsed=json.loads(line);break
                except json.JSONDecodeError:pass
        if p.returncode==0 and isinstance(parsed,dict):
            required={"ok","status","slug","displayName","folder","version","latestVersion","fileCount","fingerprint"}
            if not required.issubset(parsed) or parsed.get("ok") is not True or parsed.get("status") not in {"unchanged","would-publish","published","pending-publication","submitted"}:raise PolicyError("clawhub JSON response violates the pinned publish contract")
            for key,value in expected.items():
                if parsed.get(key)!=value:raise PolicyError(f"clawhub JSON {key} mismatch: expected {value!r}, got {parsed.get(key)!r}")
            if not isinstance(parsed["folder"],str) or not parsed["folder"] or not re.fullmatch(r"[0-9a-f]{64}",parsed["fingerprint"]):raise PolicyError("clawhub JSON folder/fingerprint invalid")
            return parsed
        if n+1==retries or not re.search(r"\b(429|50[0-4])\b|timed? out|ECONNRESET",text,re.I):raise RemoteError("clawhub command failed: "+text[:1000])
        m=re.search(r"Retry-After:\s*(\d+)",text,re.I);time.sleep(float(m.group(1)) if m else 2**n)

def publish_args(s,remote,directory,source_repo,source_commit,dry=False):
    if not SHA.fullmatch(source_commit or ""):raise PolicyError("publish source commit must be an immutable full SHA")
    args=["skill","publish",str(directory),"--slug",s["slug"],"--name",s["displayName"],"--owner",s["publisher"],"--version",s["version"],"--source-repo",source_repo,"--source-commit",source_commit,"--source-ref",source_commit,"--source-path",s["path"]]
    diff=remote.get("metadataDifferences",[])
    if s.get("categories") and "categories" in diff:args += ["--categories",",".join(s["categories"])]
    if s.get("topics") and "topics" in diff:args += ["--topics",",".join(s["topics"])]
    if dry:args.append("--dry-run")
    return args+["--json"]
def install_closure(bin,s):
    specs=[(s["publisher"],s["slug"],s["version"])]
    for value in s["runtimeDependsOn"]:
        if value.startswith("skill:"):specs.append(SKILL_DEP.fullmatch(value).groups())
    with tempfile.TemporaryDirectory(prefix="clawhub-closure-") as td:
        for p,slug,v in dict.fromkeys(specs):
            proc=subprocess.run([bin,"--workdir",td,"--dir","skills","--no-input","install",f"@{p}/{slug}","--version",v],text=True,capture_output=True)
            if proc.returncode:return {"ok":False,"identity":f"{p}/{slug}","version":v,"error":(proc.stdout+proc.stderr)[-1000:]}
            if not (Path(td)/"skills"/f"@{p}"/slug/"SKILL.md").is_file():return {"ok":False,"identity":f"{p}/{slug}","version":v,"error":"installed owner-qualified package lacks SKILL.md at skills/@owner/slug"}
        return {"ok":True,"installed":[f"{p}/{slug}@{v}" for p,slug,v in dict.fromkeys(specs)],"layout":"one isolated shared skills root","executedSkillCode":False}
def make_plan(mp,root,reg,bin=None):
    m=read(mp);validate_manifest(m,root)
    source_commit=git_head(root)
    if bin and not source_commit:raise PolicyError("plan with clawhub CLI requires a git checkout with full source SHA")
    if bin:check_cli(bin)
    items=[]
    for s in m["skills"]:
        item={k:s[k] for k in ("path","publisher","slug","version","disposition")}
        if s["disposition"]=="publish":
            fs=package(root,s);fp=fingerprint(fs);pkg=inventory_digest(fs);dry_result=None
            if bin:
                # Same locked CLI/runtime is authoritative for the localeCompare
                # fingerprint. File hashes remain the deterministic cross-runtime gate.
                with tempfile.TemporaryDirectory() as td:
                    stage(fs,Path(td));dry_result=cli(bin,publish_args(s,{"metadataDifferences":["categories","topics"]},td,m["repository"],source_commit,True),{"slug":s["slug"],"displayName":s["displayName"],"version":s["version"],"fileCount":len(fs)},1)
                fp=dry_result["fingerprint"]
            remote=inspect(reg,s,fp);item.update(artifactDigest=fp,packageDigest=pkg,files=[{k:x[k] for k in ("path","size","sha256")} for x in fs],remote=remote)
            if dry_result is not None:item["dryRun"]=dry_result
        else:item["reason"]=s["excludeReason"]
        items.append(item)
    md=digest(mp.read_bytes());sh=source_commit;workflow_sha=os.getenv("CLAWHUB_WORKFLOW_SHA");policy_sha=os.getenv("CLAWHUB_POLICY_SHA");base={"repository":m["repository"],"sourceSha":sh,"policySha":policy_sha,"workflowSha":workflow_sha,"manifestDigest":md,"cliVersion":CLI_VERSION,"artifacts":[(x["publisher"],x["slug"],x.get("artifactDigest")) for x in items]}
    return {"schemaVersion":1,"repository":m["repository"],"sourceSha":sh,"policySha":policy_sha,"workflowSha":workflow_sha,"bootstrapSha":m["bootstrapSha"],"manifestDigest":md,"cliVersion":CLI_VERSION,"provenanceDigest":digest(canonical(base)),"skills":items}
def plan_blockers(plan):
    blocked={"OWNER_MISMATCH","CONTENT_CONFLICT","CONTENT_AT_OTHER_VERSION","REMOTE_AHEAD","POLICY_DRIFT","BLOCKED_MODERATION"}
    return [x for x in plan["skills"] if x.get("disposition")=="publish" and x.get("remote",{}).get("status") in blocked]
def fresh(plan,new):
    for k in ("schemaVersion","repository","sourceSha","policySha","workflowSha","manifestDigest","cliVersion"):
        if plan.get(k)!=new.get(k):raise PolicyError(f"stale plan: {k} changed")
    a={(x["publisher"],x["slug"]):x for x in plan["skills"]};b={(x["publisher"],x["slug"]):x for x in new["skills"]}
    if a.keys()!=b.keys():raise PolicyError("stale plan: identities changed")
    for key,x in b.items():
        for f in ("version","disposition","artifactDigest","packageDigest"):
            if a[key].get(f)!=x.get(f):raise PolicyError(f"stale plan: {key} {f} changed")
def do_publish(mp,root,pp,rp,bin,reg):
    check_cli(bin);plan=read(pp);new=make_plan(mp,root,reg,bin);fresh(plan,new);m=read(mp);sm={(x["publisher"],x["slug"]):x for x in m["skills"]};results=[];ok=True
    for e in new["skills"]:
        key=(e["publisher"],e["slug"]);s=sm[key]
        if e["disposition"]!="publish":results.append({"identity":"/".join(key),"status":e["disposition"].upper()});continue
        remote=inspect(reg,s,e["artifactDigest"])
        if remote["status"]=="DISTRIBUTION_VERIFIED":results.append({"identity":"/".join(key),"status":"VERIFIED_NOOP"});continue
        if remote["status"]!="MISSING":ok=False;results.append({"identity":"/".join(key),**remote});continue
        try:
            fs=package(root,s)
            with tempfile.TemporaryDirectory() as td:stage(fs,Path(td));result=cli(bin,publish_args(s,remote,td,m["repository"],new["sourceSha"]),{"slug":s["slug"],"displayName":s["displayName"],"version":s["version"],"fileCount":len(fs),"fingerprint":e["artifactDigest"]})
            after=inspect(reg,s,e["artifactDigest"]);status=after["status"]
            if status!="DISTRIBUTION_VERIFIED":ok=False;status="PENDING_PUBLICATION" if result.get("status") in {"submitted","pending-publication"} else status
            results.append({"identity":"/".join(key),"status":status,"cli":result,"remote":after})
        except Exception as ex:ok=False;results.append({"identity":"/".join(key),"status":"FAILED","error":str(ex)})
    final=[];ok=True
    for s in m["skills"]:
        if s["disposition"]!="publish":continue
        state=inspect(reg,s,fingerprint(package(root,s)))
        if state["status"]=="DEPENDENCY_PUBLIC_VERIFIED":
            closure=install_closure(bin,s);state={**state,"status":"DISTRIBUTION_VERIFIED" if closure["ok"] else "DEPENDENCY_CLOSURE_UNVERIFIED","closure":closure}
        ok &= state["status"]=="DISTRIBUTION_VERIFIED";final.append({"identity":f"{s['publisher']}/{s['slug']}",**state})
    write(rp,{"schemaVersion":1,"repository":new["repository"],"sourceSha":new["sourceSha"],"ok":bool(ok),"results":results,"finalVerification":final});return bool(ok)
def do_verify(mp,root,rp,reg,bin=None):
    m=read(mp);validate_manifest(m,root);results=[];ok=True;authoritative={}
    if bin:authoritative={(x["publisher"],x["slug"]):x.get("artifactDigest") for x in make_plan(mp,root,reg,bin)["skills"]}
    for s in m["skills"]:
        if s["disposition"]!="publish":r={"status":s["disposition"].upper()}
        else:
            r=inspect(reg,s,authoritative.get((s["publisher"],s["slug"])) or fingerprint(package(root,s)))
            if r["status"]=="DEPENDENCY_PUBLIC_VERIFIED":
                if bin:
                    closure=install_closure(bin,s);r={**r,"status":"DISTRIBUTION_VERIFIED" if closure["ok"] else "DEPENDENCY_CLOSURE_UNVERIFIED","closure":closure}
                else:r={**r,"status":"DEPENDENCY_CLOSURE_UNVERIFIED","reason":"verify requires --clawhub-bin for same-root companion installation"}
            ok &= r["status"]=="DISTRIBUTION_VERIFIED"
        results.append({"identity":f"{s['publisher']}/{s['slug']}",**r})
    write(rp,{"schemaVersion":1,"repository":m["repository"],"ok":bool(ok),"results":results});return bool(ok)

def fetch(url):
    try:
        with urlopen(Request(url,headers={"User-Agent":"zenstory-clawhub-audit/1"}),timeout=20) as r:return json.loads(r.read().decode())
    except Exception as e:raise RemoteError(f"cannot fetch {url}: {e}") from e
def fetch_text(url):
    try:
        with urlopen(Request(url,headers={"User-Agent":"zenstory-clawhub-audit/1"}),timeout=20) as r:return r.read().decode()
    except Exception as e:raise RemoteError(f"cannot fetch {url}: {e}") from e
def audit(cp,reg):
    c=read(cp)
    if c.get("schemaVersion")!=1 or not isinstance(c.get("repositories"),list):raise PolicyError("invalid catalog")
    allowed=set(c.get("allowedPublishers",[])); fixed={(x["publisher"],x["slug"]):(x["repository"],x["path"]) for x in c.get("identities",[])}
    if len(fixed)!=len(c.get("identities",[])):raise PolicyError("catalog identity ownership is duplicated")
    findings=[];seen={};registered=set();den=exc=verified=unverified=0
    for src in c["repositories"]:
        repo=src.get("repository");registered.add(repo)
        if src.get("classification")!="canonical-public":continue
        workflow=src.get("callerWorkflow","")
        try:
            text=fetch_text(f"https://raw.githubusercontent.com/{repo}/main/{workflow}")
            refs=re.findall(r"zenstory-ai/\.github/\.github/workflows/clawhub-publish\.yml@([0-9a-f]{40}|ROOT_REPLACE)",text)
            controls=re.findall(r"control_ref:\s*([0-9a-f]{40}|ROOT_REPLACE)",text)
            if len(refs)!=1 or len(controls)!=1 or refs[0]!=controls[0] or refs[0]=="ROOT_REPLACE":
                findings.append({"key":repo+":caller","status":"POLICY_DRIFT","detail":"caller must pin matching reusable/control_ref full SHA and approved CLI policy"})
        except Exception as e:findings.append({"key":repo+":caller","status":"UNKNOWN","detail":str(e)})
        try:m=fetch(src["manifestUrl"])
        except Exception as e:findings.append({"key":repo+":manifest","status":"UNKNOWN","detail":str(e)});continue
        if m.get("schemaVersion")!=1 or m.get("repository")!=repo:findings.append({"key":repo+":manifest","status":"POLICY_DRIFT","detail":"schema/repository mismatch"});continue
        for s in m.get("skills",[]):
            key=(str(s.get("publisher","")).lower(),str(s.get("slug","")));label=f"{repo}:{key[0]}/{key[1]}"
            if key in seen:findings += [{"key":label,"status":"POLICY_DRIFT","detail":"duplicate identity with "+seen[key]}];continue
            seen[key]=repo
            if s.get("disposition")=="excluded":exc+=1;continue
            den+=1
            if s.get("disposition")!="publish":findings.append({"key":label,"status":"BLOCKED","detail":s.get("excludeReason")});continue
            if s.get("publisher") not in allowed or fixed.get((s.get("publisher"),s.get("slug")))!=(repo,s.get("path")):
                findings.append({"key":label,"status":"POLICY_DRIFT","detail":"identity is not fixed to this repository/path in central catalog"});continue
            try:meta=reg.skill(s["publisher"],s["slug"]);vd=reg.version(s["publisher"],s["slug"],s["version"])
            except RemoteError as e:findings.append({"key":label,"status":"UNKNOWN","detail":str(e)});continue
            if not meta:st,detail="MISSING","owner-qualified public entry absent"
            elif owner(meta) and owner(meta).lower()!=s["publisher"].lower():st,detail="OWNER_MISMATCH",owner(meta)
            elif not vd:st,detail="STALE",f"version {s['version']} absent"
            else:
                got,_=remote_inventory(vd);remote_pkg=remote_package_digest(vd)
                try:scan=reg.scan(s["publisher"],s["slug"],s["version"])
                except RemoteError as e:findings.append({"key":label,"status":"UNKNOWN","detail":str(e)});continue
                sec=scan.get("security",{}) if isinstance(scan,dict) else {}
                expected_pkg=s.get("packageDigest")
                if not isinstance(expected_pkg,str) or not re.fullmatch(r"[0-9a-f]{64}",expected_pkg):findings.append({"key":label,"status":"POLICY_DRIFT","detail":"manifest packageDigest missing or invalid"});continue
                if remote_pkg and remote_pkg!=expected_pkg:findings.append({"key":label,"status":"CONTENT_CONFLICT","detail":f"remote packageDigest {remote_pkg} differs from expected {expected_pkg}"});continue
                if remote_pkg==expected_pkg and sec.get("status")=="clean" and sec.get("hasScanResult") is True:verified+=1;continue
                if got and sec.get("status")=="clean" and sec.get("hasScanResult") is True:unverified+=1;continue
                st,detail="UNKNOWN","public version file hashes or aggregate clean scan unavailable"
            findings.append({"key":label,"status":st,"detail":detail})
    try: public={x["full_name"] for x in fetch("https://api.github.com/orgs/zenstory-ai/repos?per_page=100&type=public")}
    except Exception as e:public=set();findings.append({"key":"zenstory-ai:repository-discovery","status":"UNKNOWN","detail":str(e)})
    for repo in sorted(public-registered):findings.append({"key":repo+":onboarding","status":"POLICY_DRIFT","detail":"public repository unclassified"})
    return {"schemaVersion":1,"generatedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"coverage":{"verified":verified,"unverifiedHealthy":unverified,"denominator":den,"excluded":exc,"percent":100*verified/den if den else 100,"note":"unverifiedHealthy is not counted as verified and does not create an incident without an immutable expected digest"},"findings":findings}

def parser():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
    v=s.add_parser("validate");v.add_argument("--manifest",type=Path,required=True);v.add_argument("--repo-root",type=Path,required=True);v.add_argument("--base-ref")
    q=s.add_parser("plan");q.add_argument("--manifest",type=Path,required=True);q.add_argument("--repo-root",type=Path,required=True);q.add_argument("--output",type=Path,required=True);q.add_argument("--clawhub-bin")
    q=s.add_parser("publish");q.add_argument("--manifest",type=Path,required=True);q.add_argument("--repo-root",type=Path,required=True);q.add_argument("--plan",type=Path,required=True);q.add_argument("--report",type=Path,required=True);q.add_argument("--clawhub-bin",required=True)
    q=s.add_parser("verify");q.add_argument("--manifest",type=Path,required=True);q.add_argument("--repo-root",type=Path,required=True);q.add_argument("--report",type=Path,required=True);q.add_argument("--clawhub-bin")
    q=s.add_parser("audit");q.add_argument("--catalog",type=Path,required=True);q.add_argument("--output",type=Path,required=True)
    q=s.add_parser("lock");q.add_argument("--manifest",type=Path,required=True);q.add_argument("--repo-root",type=Path,required=True);q.add_argument("--output",type=Path)
    return p
def main(argv=None):
    a=parser().parse_args(argv)
    try:
        if a.cmd=="validate":m=read(a.manifest);validate_manifest(m,a.repo_root.resolve());print(json.dumps({"ok":True,"repository":m["repository"]}));return 0
        reg=Registry()
        if a.cmd=="plan":
            value=make_plan(a.manifest,a.repo_root.resolve(),reg,a.clawhub_bin);write(a.output,value)
            if plan_blockers(value):print("error: publish plan contains owner/version/content/policy blockers",file=sys.stderr);return 2
            return 0
        if a.cmd=="publish":return 0 if do_publish(a.manifest,a.repo_root.resolve(),a.plan,a.report,a.clawhub_bin,reg) else 2
        if a.cmd=="verify":
            if a.clawhub_bin:check_cli(a.clawhub_bin)
            return 0 if do_verify(a.manifest,a.repo_root.resolve(),a.report,reg,a.clawhub_bin) else 2
        if a.cmd=="audit":write(a.output,audit(a.catalog,reg));return 0
        if a.cmd=="lock":
            m=read(a.manifest);root=a.repo_root.resolve()
            for s in m.get("skills",[]):
                if s.get("disposition")=="publish":s["packageDigest"]=inventory_digest(package(root,s))
            target=a.output or a.manifest;validate_manifest(m,root);write(target,m);print(json.dumps({"ok":True,"output":str(target)}));return 0
    except (PolicyError,RemoteError) as e:print("error:",e,file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
