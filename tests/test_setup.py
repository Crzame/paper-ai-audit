import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from setup_models import configure

class PortableConfigurationChecks(unittest.TestCase):
    def test_local_configuration_uses_actual_verified_paths_without_mutating_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'checkpoints/test_model';folder.mkdir(parents=True)
            payload=b'local test checkpoint metadata'
            (folder/'config.json').write_bytes(payload)
            manifest={'models':[{'key':'test_model','local_path':'${MODEL_ROOT}/test_model',
                'files':[{'name':'config.json','sha256':hashlib.sha256(payload).hexdigest()}]}]}
            target=root/'models.local.json'
            configured=configure(manifest,target,model_root=root/'checkpoints')
            self.assertEqual(Path(configured['models'][0]['local_path']),folder.resolve())
            self.assertEqual(manifest['models'][0]['local_path'],'${MODEL_ROOT}/test_model')
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')),configured)
    def test_mismatched_checkpoint_is_not_published_as_valid_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'test_model';folder.mkdir()
            (folder/'config.json').write_bytes(b'wrong content')
            manifest={'models':[{'key':'test_model','files':[{'name':'config.json','sha256':'0'*64}]}]}
            target=root/'models.local.json'
            with self.assertRaises(ValueError):configure(manifest,target,model_root=root)
            self.assertFalse(target.exists())

if __name__=='__main__':unittest.main(verbosity=2)
