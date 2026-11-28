// Exact 45.3.2 internal component adapter, not local-mode PR generation.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [dist, root, cache, depName, oldVersion, newVersion, mode] = process.argv.slice(2);
const imp = (name) => import(pathToFileURL(path.join(dist, name)).href);
const { GlobalConfig } = await imp('config/global.js');
const { extractPackageFile } = await imp('modules/manager/pep621/extract.js');
const { doAutoReplace } = await imp('workers/repository/update/branch/auto-replace.js');
const { updateArtifacts } = await imp('modules/manager/pep621/artifacts.js');
GlobalConfig.set({
  localDir: root, cacheDir: cache, containerbaseDir: path.join(cache, 'containerbase'),
  binarySource: 'global', platform: 'local',
  allowScripts: false, allowPlugins: false, allowedCommands: [],
  allowedUnsafeExecutions: [], exposeAllEnv: false,
});
const file = 'pyproject.toml';
const original = await fs.readFile(path.join(root, file), 'utf8');
const extracted = await extractPackageFile(original, file);
const deps = extracted?.deps ?? [];
const indices = deps.map((d, i) => d.packageName === depName &&
  d.currentValue === '==' + oldVersion ? i : -1).filter(i => i >= 0);
if (indices.length !== 1) throw Error('target missing or ambiguous');
const depIndex = indices[0];
const upgrade = {
  ...deps[depIndex], depName, manager:'pep621', packageFile:file, depIndex,
  newValue: '==' + newVersion, newVersion, updateType:'patch',
};
let updated = await doAutoReplace(upgrade, original, false);
if (typeof updated !== 'string') throw Error('replacement did not return text');
if (mode === 'conflict') {
  updated = updated.replace('"' + depName + '==' + newVersion + '"',
    '"' + depName + '==' + newVersion + '", "' + depName + '==' + oldVersion + '"');
}
const results = await updateArtifacts({
  packageFileName:file, newPackageFileContent:updated, updatedDeps:[upgrade], config:{},
});
const artifacts = (results ?? []).map(x => ({
  file:x.file?.path ?? x.file?.name ?? null,
  error:x.artifactError ?? null,
  contentsPresent:x.file?.contents !== undefined,
}));
if (mode !== 'conflict' && artifacts.length === 1 &&
    artifacts[0].file === 'uv.lock' && artifacts[0].error === null &&
    artifacts[0].contentsPresent) {
  await fs.writeFile(path.join(root, 'uv.lock'), results[0].file.contents);
  await fs.writeFile(path.join(root, file), updated);
}
const repeated = mode === 'conflict' ? null :
  await doAutoReplace(upgrade, updated, false, false);
console.log(JSON.stringify({msg:'E017 component result',level:30,
  manifest:updated, repeatedManifest:repeated, artifacts}));
