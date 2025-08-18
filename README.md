# GitOps-Style Package Repository Management

## Tools
- **debrepoctl**: Primary tool for repository management

## Import Functionality
- **Sources.gz Import**:
  - Imports into a directory tree structure based on the `Directory` field
  - Filename format: `PackageName_Version.dsc`
  - Contents: Standard stanza format
  - Serves as a manifest describing either:
    - Current state (unmodified)
    - Desired state (modified)

- **Packages.gz Import**:
  - Similar structure to Sources.gz
  - Filename derived from the `Filename` field
  - Also functions as a manifest

- **Pool Directory**:
  - Imported as a single file to reduce gitfs load

## Workflow

### Repository Structure
- Package repositories (e.g., Trixie, Sid) are automatically imported into separate Git repositories
- Each repository uses the `main` branch
- Trigger: Repository modification by the runner
- **Key Property**: `main` branch always reflects the current state of the actual repository

### Administrator Workflow
1. Administrator primarily works with the Sources tree
2. Work process:
   - Create a new branch from `main` (e.g., `gnome49-backport`)
   - Make changes in the new branch
   - Push changes to Git
3. Runner actions:
   - Compares the push branch (e.g., `gnome49-backport`) with `main`
   - Applies changes to the actual repository
   - Calls `debrepoctl` to re-import
   - Updates `main` branch

### Export Functionality
- Converts directory trees with stanza files back to:
  - `Sources.gz`
  - `Packages.gz`
- Purpose: Supports `dose-*check` operations

### Snapshot Capability
- Since the pool contents are only appended:
  - `Sources.gz` and `Packages.gz` can serve as snapshots for any date

### Partial Build Recovery
- If only some packages build successfully:
  1. In the working branch (e.g., `gnome49-backport`):
     - Perform `git revert`
     - Perform `git rebase`
  2. This allows reattempting the operation

## Example Git Diff Output
```
$ git diff master --name-status
D       dists/trixie/main/binary-amd64/aiobafi6/python3-aiobafi6_0.9.0-2_all.deb
A       dists/trixie/main/binary-amd64/canna/canna-utils_3.7p3-25_amd64.deb
A       dists/trixie/main/binary-amd64/canna/canna_3.7p3-25_amd64.deb
A       dists/trixie/main/binary-amd64/canna/libcanna1g-dev_3.7p3-25_amd64.deb
A       dists/trixie/main/binary-amd64/canna/libcanna1g_3.7p3-25_amd64.deb
```

## import 

`debrepoctl --import-repo http://deb.debian.org/debian/ path/to/gitrepo`
`debrepoctl --import-repo file:///path/to/debian/ path/to/gitrepo`

`./debrepoctl.py --import-repo https://ftp.debian.org/debian/ --output-dir tests-out --distributions trixie`

## export 

`debrepoctl --export-file path/to/gitrepo:branch Packages`

## main branch

main branch sync 1h

main branch - real repo
branching
commit
commit
push
git diff main...HEAD
git diff master --name-status
