import importlib.util,io,json,subprocess,tempfile,unittest
from email.message import Message
from urllib.error import HTTPError
from pathlib import Path
from unittest import mock
P=Path(__file__).parents[1]/"scripts/clawhub_release.py";S=importlib.util.spec_from_file_location("release",P);r=importlib.util.module_from_spec(S);S.loader.exec_module(r)
class Remote:
 def __init__(self,meta=None,version=None,resolved=None,scan=None):self.meta=meta;self.v=version;self.resolved=resolved;self.s=scan or {"security":{"status":"clean","hasScanResult":True,"hasWarnings":True}}
 def resolve(self,*a):return self.resolved
 def skill(self,*a):return self.meta
 def version(self,*a):return self.v
 def scan(self,*a):return self.s
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);d=self.root/"skills/a";d.mkdir(parents=True);(d/"SKILL.md").write_bytes(b"# A\n");(d/"x.py").write_bytes(b"x\n");(self.root/"LICENSE").write_text("MIT\n")
  self.m={"schemaVersion":1,"repository":"zenstory-ai/example","skillRoots":["skills"],"bootstrapSha":"a"*40,"skills":[{"path":"skills/a","slug":"a","publisher":"worldwonderer","version":"1.0.0","displayName":"A","disposition":"publish","excludeReason":"","maintainer":"@m","include":["**/*"],"rebuildOn":[],"runtimeDependsOn":[],"supportedRuntimes":[],"categories":["creative"],"topics":["fiction"],"rights":{"status":"permission-recorded","evidence":".clawhub/README.md"}}]}
  self.m["skills"][0]["packageDigest"]=r.inventory_digest(r.package(self.root,self.m["skills"][0]))
 def tearDown(self):self.t.cleanup()
 def test_schema_and_license(self):r.validate_manifest(self.m,self.root);self.assertEqual(["LICENSE","SKILL.md","x.py"],[x["path"] for x in r.package(self.root,self.m["skills"][0])])
 def test_cli_hidden_paths_are_not_packaged(self):
  (self.root/"skills/a/.gitkeep").write_text("");d=self.root/"skills/a/node_modules";d.mkdir();(d/"x.js").write_text("x");self.assertNotIn(".gitkeep",[x["path"] for x in r.package(self.root,self.m["skills"][0])]);self.assertNotIn("node_modules/x.js",[x["path"] for x in r.package(self.root,self.m["skills"][0])])
 def test_unclassified(self):
  d=self.root/"skills/b";d.mkdir();(d/"SKILL.md").write_text("b")
  with self.assertRaisesRegex(r.PolicyError,"unclassified"):r.validate_manifest(self.m,self.root)
 def test_escape_secret_symlink(self):
  self.m["skills"][0]["include"]=["../x"]
  with self.assertRaises(r.PolicyError):r.validate_manifest(self.m,self.root)
  self.m["skills"][0]["include"]=["**/*"];(self.root/"skills/a/.env").write_text("x")
  with self.assertRaisesRegex(r.PolicyError,"unsafe"):r.package(self.root,self.m["skills"][0])
 def test_intermediate_directory_symlink_escape(self):
  outside=self.root/"outside";outside.mkdir();(outside/"leak.txt").write_text("leak");(self.root/"skills/a/link").symlink_to(outside,target_is_directory=True);self.m["skills"][0]["include"]=["SKILL.md","link/*"]
  with self.assertRaisesRegex(r.PolicyError,"symlink"):r.package(self.root,self.m["skills"][0])
 def test_rights_and_dependency_contract(self):
  self.m["skills"][0]["rights"]["status"]="unconfirmed"
  with self.assertRaisesRegex(r.PolicyError,"rights"):r.validate_manifest(self.m,self.root)
  self.m["skills"][0]["rights"]["status"]="permission-recorded";self.m["skills"][0]["runtimeDependsOn"]=["skill:b"]
  with self.assertRaisesRegex(r.PolicyError,"skill dependency"):r.validate_manifest(self.m,self.root)
  self.m["skills"][0]["runtimeDependsOn"]=["skill:worldwonderer/b@1.2.3"];self.m["skills"][0]["packageDigest"]=r.inventory_digest(r.package(self.root,self.m["skills"][0]));r.validate_manifest(self.m,self.root);fs=r.package(self.root,self.m["skills"][0]);install=next(x for x in fs if x["path"]=="INSTALL.md");self.assertIn(b"@worldwonderer/b --version 1.2.3",install["bytes"])
  self.m["skills"][0]["runtimeDependsOn"]=["skill:other/b@1.2.3"]
  with self.assertRaisesRegex(r.PolicyError,"cross-owner"):r.validate_manifest(self.m,self.root)
 def test_public_skill_topics_are_compared_but_absent_categories_unobserved(self):
  s=self.m["skills"][0];meta={"skill":{"displayName":"A","topics":["different"]},"metadata":None};self.assertEqual(["topics"],r.metadata_diff(meta,s));self.assertEqual(["categories"],r.metadata_unobserved(meta,s))
 @mock.patch.object(r.subprocess,"run")
 def test_install_closure_checks_owner_qualified_layout(self,run):
  def install(args,**kwargs):
   root=Path(args[args.index("--workdir")+1]);identity=args[args.index("install")+1];owner,slug=identity[1:].split("/");d=root/"skills"/f"@{owner}"/slug;d.mkdir(parents=True);(d/"SKILL.md").write_text("ok");return subprocess.CompletedProcess(args,0,"","")
  run.side_effect=install;self.assertTrue(r.install_closure("clawhub",self.m["skills"][0])["ok"])
 def test_fingerprint_deterministic(self):
  fs=r.package(self.root,self.m["skills"][0]);self.assertEqual(r.fingerprint(fs),r.fingerprint(reversed(fs)))
 def test_cli_locale_order_fingerprint_vector(self):
  files=[{"path":"LICENSE","sha256":"8624846d707ae75855b7ac2a18e65d11d29738caeb0a4c4c5cedf88066f2f5b1"},{"path":"SKILL.md","sha256":"79aada543bbc876e7d79e4989cc87067ed7e01d613933157689855c7b8d14b0b"},{"path":"agents/openai.yaml","sha256":"6340d41c7dbcacc55aefef0faf795a5eda0cb38a8b83589b053ea43812b71490"},{"path":"references/art-direction-method.md","sha256":"7f90baf826dda2c94b3622c5419515e348c5efe1abdc802c5a25346bb6c073eb"}]
  self.assertEqual("351de3eab24f1c780c74c87d700a2c612599f47e32a16f76f06d81bfe39fc704",r.fingerprint(files))
 def test_publish_args_pin_identity_and_source(self):
  a=r.publish_args(self.m["skills"][0],{"metadataDifferences":["categories"]},"/tmp/pkg","zenstory-ai/example","a"*40,True);self.assertIn("--slug",a);self.assertIn("--name",a);self.assertIn("--source-commit",a);self.assertNotIn("--migrate-owner",a)
 def test_owner_conflict(self):self.assertEqual("OWNER_MISMATCH",r.inspect(Remote(meta={"owner":{"handle":"other"}}),self.m["skills"][0],"0"*64)["status"])
 def test_remote_ahead_blocks_downgrade(self):
  remote=Remote(resolved={"match":None,"latestVersion":{"version":"2.0.0"}});self.assertEqual("REMOTE_AHEAD",r.inspect(remote,self.m["skills"][0],"0"*64)["status"])
 def test_generated_card_only_ignored_and_warnings_preserved(self):
  s=self.m["skills"][0];fs=r.package(self.root,s);remote=[{k:x[k] for k in ("path","size","sha256")} for x in fs]+[{"path":"skill-card.md","size":1,"sha256":"f"*64}]
  reg=Remote(meta={"owner":{"handle":"worldwonderer"},"displayName":"A","categories":["creative"],"topics":["fiction"]},version={"version":{"files":remote}});out=r.inspect(reg,s,r.fingerprint(fs));self.assertEqual("DISTRIBUTION_VERIFIED",out["status"]);self.assertTrue(out["security"]["hasWarnings"])
  remote.append({"path":"other","size":1,"sha256":"e"*64});self.assertEqual("CONTENT_CONFLICT",r.inspect(reg,s,r.fingerprint(fs))["status"])
 @mock.patch.object(r.time,"sleep")
 @mock.patch.object(r.subprocess,"run")
 def test_bounded_retry(self,run,sleep):
  body={"ok":True,"status":"published","slug":"s","displayName":"S","folder":"/tmp/x","version":"1.0.0","latestVersion":None,"fileCount":1,"fingerprint":"a"*64};run.side_effect=[subprocess.CompletedProcess([],1,"","HTTP 429 Retry-After: 0"),subprocess.CompletedProcess([],0,json.dumps(body,indent=2),"")];self.assertEqual("published",r.cli("c",["x"],{"slug":"s","version":"1.0.0"})["status"]);self.assertEqual(2,run.call_count)
 @mock.patch.object(r.time,"sleep")
 @mock.patch.object(r,"urlopen")
 def test_registry_closes_not_found_without_retry(self,urlopen,sleep):
  error=HTTPError("https://clawhub.ai/x",404,"not found",Message(),io.BytesIO());urlopen.side_effect=error
  self.assertIsNone(r.Registry().get("/x",{}));self.assertTrue(error.closed);self.assertEqual(1,urlopen.call_count);sleep.assert_not_called()
 @mock.patch.object(r.time,"sleep")
 @mock.patch.object(r,"urlopen")
 def test_registry_retries_timeout_then_succeeds(self,urlopen,sleep):
  response=mock.MagicMock();response.__enter__.return_value.read.return_value=b'{"ok":true}';urlopen.side_effect=[TimeoutError("slow"),TimeoutError("slow"),response];self.assertEqual({"ok":True},r.Registry().get("/x",{}));self.assertEqual(3,urlopen.call_count);self.assertEqual([mock.call(1),mock.call(2)],sleep.call_args_list)
 @mock.patch.object(r.time,"sleep")
 @mock.patch.object(r,"urlopen")
 def test_registry_honors_clamped_retry_after_for_429(self,urlopen,sleep):
  headers=Message();headers["Retry-After"]="99";error=HTTPError("https://clawhub.ai/x",429,"limited",headers,io.BytesIO());response=mock.MagicMock();response.__enter__.return_value.read.return_value=b'{}';urlopen.side_effect=[error,response];self.assertEqual({},r.Registry().get("/x",{}));sleep.assert_called_once_with(30.0);self.assertTrue(error.closed)
 @mock.patch.object(r.time,"sleep")
 @mock.patch.object(r,"urlopen")
 def test_registry_does_not_retry_unauthorized(self,urlopen,sleep):
  error=HTTPError("https://clawhub.ai/x",401,"unauthorized",Message(),io.BytesIO());urlopen.side_effect=error
  with self.assertRaisesRegex(r.RemoteError,"401"):r.Registry().get("/x",{})
  self.assertEqual(1,urlopen.call_count);sleep.assert_not_called();self.assertTrue(error.closed)
 @mock.patch.object(r.time,"sleep")
 @mock.patch.object(r,"urlopen")
 def test_registry_stops_after_three_retryable_5xx(self,urlopen,sleep):
  error=HTTPError("https://clawhub.ai/x",503,"down",Message(),io.BytesIO());urlopen.side_effect=error
  with self.assertRaisesRegex(r.RemoteError,"503"):r.Registry().get("/x",{})
  self.assertEqual(3,urlopen.call_count);self.assertEqual([mock.call(1),mock.call(2)],sleep.call_args_list);self.assertTrue(error.closed)
 @mock.patch.object(r.subprocess,"run")
 def test_cli_contract_rejects_missing_field_even_with_extra(self,run):
  body={"ok":True,"status":"published","slug":"s","displayName":"S","folder":"/tmp/x","version":"1.0.0","fileCount":1,"fingerprint":"a"*64,"extra":1};run.return_value=subprocess.CompletedProcess([],0,json.dumps(body),"")
  with self.assertRaisesRegex(r.PolicyError,"contract"):r.cli("c",["x"],{"slug":"s"})
 def test_stale_plan(self):
  a={"schemaVersion":1,"repository":"r","sourceSha":"s","manifestDigest":"m","cliVersion":"0.23.3","skills":[{"publisher":"p","slug":"s","version":"1.0.0","disposition":"publish","artifactDigest":"x"}]};b=json.loads(json.dumps(a));r.fresh(a,b);b["skills"][0]["version"]="1.0.1"
  with self.assertRaisesRegex(r.PolicyError,"version changed"):r.fresh(a,b)
 def test_lock_populates_cross_platform_inventory_digest(self):
  del self.m["skills"][0]["packageDigest"];source=self.root/"publish.json";output=self.root/"locked.json";source.write_text(json.dumps(self.m));
  with mock.patch("sys.stdout",new=io.StringIO()):self.assertEqual(0,r.main(["lock","--manifest",str(source),"--repo-root",str(self.root),"--output",str(output)]))
  locked=json.loads(output.read_text());self.assertRegex(locked["skills"][0]["packageDigest"],r"^[0-9a-f]{64}$")
 def test_plan_blockers_include_same_version_conflict_and_remote_ahead(self):
  plan={"skills":[{"disposition":"publish","remote":{"status":"CONTENT_CONFLICT"}},{"disposition":"publish","remote":{"status":"REMOTE_AHEAD"}},{"disposition":"publish","remote":{"status":"MISSING"}}]};self.assertEqual(2,len(r.plan_blockers(plan)))
 def test_base_manifest_requires_version_bump_for_package_or_catalog_changes(self):
  previous=json.loads(json.dumps(self.m));current=json.loads(json.dumps(self.m));current["skills"][0]["packageDigest"]="f"*64
  with self.assertRaisesRegex(r.PolicyError,"packageDigest"):r.compare_base_manifest(current,previous)
  current=json.loads(json.dumps(self.m));current["skills"][0]["topics"]=["changed"]
  with self.assertRaisesRegex(r.PolicyError,"topics"):r.compare_base_manifest(current,previous)
  current["skills"][0]["version"]="1.0.1";r.compare_base_manifest(current,previous);r.compare_base_manifest(current,None)
 def test_offline_validation_never_constructs_registry(self):
  path=self.root/"publish.json";path.write_text(json.dumps(self.m))
  with mock.patch.object(r.Registry,"get",side_effect=AssertionError("network used")):out=r.offline_validation(path,self.root)
  self.assertTrue(out["offline"]);self.assertGreater(out["skills"][0]["fileCount"],0)
 def test_offline_validation_rejects_manifest_outside_repo_with_base_ref(self):
  with tempfile.TemporaryDirectory() as outside:
   path=Path(outside)/"publish.json";path.write_text(json.dumps(self.m))
   with self.assertRaisesRegex(r.PolicyError,"inside repo-root"):r.offline_validation(path,self.root,base_ref="b"*40)
 @mock.patch.object(r.shutil,"which",return_value="/usr/bin/node")
 @mock.patch.object(r.subprocess,"run")
 def test_sdk_inventory_rejects_any_file_set_difference(self,run,which):
  package_root=self.root/"sdk";cli=package_root/"bin/clawdhub.js";module=package_root/"dist/skills.js";cli.parent.mkdir(parents=True);module.parent.mkdir();cli.write_text("#!/usr/bin/env node\n");module.write_text("export {}\n");run.return_value=subprocess.CompletedProcess([],0,json.dumps([{"files":[],"fingerprint":"a"*64}]),"")
  with self.assertRaisesRegex(r.PolicyError,"differs"):r.sdk_inventories(str(cli),[r.package(self.root,self.m["skills"][0])])
 def test_audit_verifies_locked_inventory_and_flags_drift_or_missing_lock(self):
  repo=self.m["repository"];sha="b"*40;catalog={"schemaVersion":1,"allowedPublishers":["worldwonderer"],"identities":[{"publisher":"worldwonderer","slug":"a","repository":repo,"path":"skills/a"}],"repositories":[{"repository":repo,"classification":"canonical-public","manifestUrl":"https://raw.example/manifest","callerWorkflow":".github/workflows/publish-clawhub.yml"}]};cp=self.root/"catalog.json";cp.write_text(json.dumps(catalog));files=r.package(self.root,self.m["skills"][0]);remote_files=[{k:x[k] for k in ("path","size","sha256")} for x in files];reg=Remote(meta={"owner":{"handle":"worldwonderer"}},version={"version":{"files":remote_files}})
  caller=f"uses: zenstory-ai/.github/.github/workflows/clawhub-publish.yml@{sha}\n  control_ref: {sha}\n"
  def fetched(url):return [] if "api.github.com" in url else self.m
  with mock.patch.object(r,"fetch",side_effect=fetched),mock.patch.object(r,"fetch_text",return_value=caller):out=r.audit(cp,reg)
  self.assertEqual(1,out["coverage"]["verified"]);self.assertEqual([],out["findings"])
  reg.v["version"]["files"].append({"path":"extra.txt","size":1,"sha256":"e"*64})
  with mock.patch.object(r,"fetch",side_effect=fetched),mock.patch.object(r,"fetch_text",return_value=caller):out=r.audit(cp,reg)
  self.assertEqual("CONTENT_CONFLICT",out["findings"][0]["status"])
  reg.v["version"]["files"].pop();del self.m["skills"][0]["packageDigest"]
  with mock.patch.object(r,"fetch",side_effect=fetched),mock.patch.object(r,"fetch_text",return_value=caller):out=r.audit(cp,reg)
  self.assertEqual("POLICY_DRIFT",out["findings"][0]["status"])
if __name__=="__main__":unittest.main()
