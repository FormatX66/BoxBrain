"""Execute shipped Wi-Fi JavaScript against a tiny DOM and deferred fetch fixture."""
from pathlib import Path
import shutil
import subprocess
import unittest


class WifiHtmlOwnershipTests(unittest.TestCase):
    def test_duplicate_actions_and_failed_fetch_preserve_input_and_release_controls(self):
        node = shutil.which("node") or shutil.which("nodejs")
        if not node:
            self.skipTest("Node.js required for executed HTML action test")
        source = (Path(__file__).parents[1] / "aurum_hopper_gui.py").read_text(encoding="utf-8")
        actions = source.split("let wifiBusy=false;", 1)[1].split("document.getElementById('wifi-scan').addEventListener", 1)[0]
        program = r"""
const assert=require('node:assert/strict');
const controls=Object.fromEntries(['wifi-ssid','wifi-password','wifi-detail','wifi-connect','wifi-scan'].map(id=>[id,{value:'',disabled:false,textContent:''}]));
const document={getElementById:id=>controls[id],querySelectorAll:()=>Object.values(controls)};
const csrf='synthetic';const show=()=>{};const confirm=()=>true;const refresh=async()=>{};
let calls=[],resolveFetch;
let fetch=async(url,options)=>{calls.push(JSON.parse(options.body));return await new Promise(resolve=>{resolveFetch=resolve})};
let wifiBusy=false;
""" + actions + r"""
(async()=>{
  controls['wifi-ssid'].value='Synthetic';controls['wifi-password'].value='test-only';
  const pending=wifiConnect();
  await wifiConnect();await wifiScan();await wifiDisconnect();await wifiForget();
  assert.equal(calls.length,1);assert.equal(calls[0].action,'connect');
  assert.equal(controls['wifi-password'].disabled,true);
  resolveFetch({ok:true,json:async()=>({result:{status:'wifi-operation-busy',saved:false}})});
  await pending;
  assert.equal(controls['wifi-password'].value,'test-only');
  assert.equal(controls['wifi-password'].disabled,false);
  fetch=async()=>{throw new Error('Failed to fetch')};await wifiConnect();
  assert.equal(controls['wifi-password'].value,'test-only');assert.equal(wifiBusy,false);
  fetch=async()=>({ok:true,json:async()=>({result:{status:'wifi-manager-conflict'}})});
  await wifiForget();assert.equal(controls['wifi-ssid'].value,'Synthetic');
  assert.equal(controls['wifi-password'].value,'test-only');
  fetch=async()=>({ok:true,json:async()=>({result:{status:'online',saved:true}})});
  await wifiConnect();assert.equal(controls['wifi-password'].value,'');assert.equal(wifiBusy,false);
  console.log('executed duplicate/busy/fetch-failure/forget-conflict/success cases passed');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
        result = subprocess.run([node, "-"], input=program, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cases passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
