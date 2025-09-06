# GitOps-Style Package Repository Management

The system employs a GitOps-style approach for managing package repositories, using debrepoctl as the primary management tool. Its import functionality handles Sources.gz files by importing them into a directory tree structure organized by the Directory field, with individual files named in the `PackageName_Version.dsc` format and containing standard stanzas. These files act as manifests that can represent either the current unmodified state or a desired modified state of the repository. The Packages.gz import follows a similar structure, with filenames derived from the Filename field, and also serves as a manifest. To minimize load on the git filesystem, the contents of the pool directory are imported as a single file.

The workflow is built around a repository structure where different package repositories, such as `Trixie` or `Sid`, are automatically imported into separate Git repositories, each using the main branch. A key property of this system is that the main branch always accurately reflects the current state of the actual repository, with any modification by the runner acting as the trigger for an update.

An administrator's workflow involves primarily working with the Sources tree. The process begins by creating a new branch from main (for example, gnome49-backport), making the necessary changes within this new branch, and then pushing those changes to Git. The runner then automatically compares this push branch against the main branch, applies the detected changes to the actual repository, calls debrepoctl to perform a re-import, and finally updates the main branch to match the new state.

The system also includes export functionality, which converts these directory trees containing stanza files back into Sources.gz and Packages.gz files. This is particularly useful for supporting *dose-check* operations. Furthermore, because the pool's contents are only ever appended to and never deleted, the `Sources.gz` and `Packages.gz` files can effectively serve as historical snapshots for any given date.

Finally, the model supports partial build recovery. If only some packages build successfully, the administrator can simply perform a git revert or git rebase in the working branch (e.g., gnome49-backport), which allows the operation to be easily reattempted.

## import 

```
./debrepoctl.py --import-gz http://deb.debian.org/debian/dists/trixie/main/source/Sources.gz -o /tmp/debian/dists/trixie/main/source/
./debrepoctl.py --import-gz http://deb.debian.org/debian/dists/forky/main/source/Sources.gz -o /tmp/debian/dists/forky/main/source/
```

## git init

```
cd /tmp/debian/dists/trixie
git init
git add -A
git commit -m "init"
```

```
cd /tmp/debian/dists/forky
git init
git add -A
git commit -m "init"
```

## git new branch

```
cd /tmp/debian/dists/trixie
git checkout -b gnome-backport 
```

## export 

`./debrepoctl.py -e -i /tmp/debian/dists/forky/main/source/ > /tmp/forky_Sources`

`./debrepoctl.py -e -i /tmp/debian/dists/trixie/main/source/ > /tmp/trixie_Sources`

## get gnome backport list

`grep-dctrl -n -s Package,Version,Section '' /tmp/trixie_Sources | tr -s "\n" | paste -d = - - - | grep '=gnome' | sed 's/=gnome//' > gnome.remove.list`

`grep-dctrl -n -s Package,Version,Section '' /tmp/forky_Sources | tr -s "\n" | paste -d = - - - | grep '=gnome' | sed 's/=gnome//' > gnome.copy.list`

## backport (remove and copy)

```
cd /tmp/debian/dists/trixie
git switch gnome-backport
cd -
```

`cat gnome.remove.list | ./debrepoctl.py --remove -o /tmp/debian/dists/trixie/main/source/`

`cat gnome.copy.list | ./debrepoctl.py --copy -i /tmp/debian/dists/forky/main/source/ -o /tmp/debian/dists/trixie/main/source/`

```
cd /tmp/debian/dists/trixie/
git add -A
git commit -am "backport"
```

## git diff

`git diff main --name-status --no-renames --`

```
D       main/source/a/almanah/almanah_0.12.4-1.dsc
A       main/source/a/almanah/almanah_0.12.4-2.dsc
D       main/source/e/eog-plugins/eog-plugins_44.1-3.dsc
A       main/source/e/eog-plugins/eog-plugins_44.1-4.dsc
D       main/source/e/eog/eog_47.0-1.dsc
A       main/source/e/eog/eog_47.0-2.dsc
D       main/source/e/epiphany-browser/epiphany-browser_48.3-2.dsc
A       main/source/e/epiphany-browser/epiphany-browser_48.5-2.dsc
D       main/source/e/evince/evince_48.1-3.dsc
A       main/source/e/evince/evince_48.1-4.dsc
D       main/source/e/evolution-data-server/evolution-data-server_3.56.1-2.dsc
A       main/source/e/evolution-data-server/evolution-data-server_3.56.2-3.dsc
D       main/source/e/evolution-ews/evolution-ews_3.56.1-1.dsc
A       main/source/e/evolution-ews/evolution-ews_3.56.2-2.dsc
D       main/source/e/evolution/evolution_3.56.1-1.dsc
A       main/source/e/evolution/evolution_3.56.2-2.dsc
D       main/source/g/gbonds/gbonds_2.0.3-17.dsc
D       main/source/g/gcr/gcr_3.41.2-3.dsc
A       main/source/g/gcr/gcr_3.41.2-4.dsc
D       main/source/g/gdm3/gdm3_48.0-2.dsc
A       main/source/g/gdm3/gdm3_48.0-3.dsc
D       main/source/g/gnome-backgrounds/gnome-backgrounds_48.2.1-1.dsc
A       main/source/g/gnome-backgrounds/gnome-backgrounds_49~beta-1.dsc
A       main/source/g/gnome-control-center/gnome-control-center_1:48.4-1.dsc
D       main/source/g/gnome-keyring/gnome-keyring_48.0-1.dsc
A       main/source/g/gnome-keyring/gnome-keyring_48.0-3.dsc
A       main/source/g/gnome-online-accounts/gnome-online-accounts_3.54.5-1.dsc
D       main/source/g/gnome-settings-daemon/gnome-settings-daemon_48.1-1.dsc
A       main/source/g/gnome-settings-daemon/gnome-settings-daemon_48.1-2.dsc
D       main/source/g/gnome-shell-extensions/gnome-shell-extensions_48.2-1.dsc
A       main/source/g/gnome-shell-extensions/gnome-shell-extensions_48.3-1.dsc
A       main/source/g/gnome-shell/gnome-shell_48.4-1.dsc
D       main/source/g/gnome-user-share/gnome-user-share_48.0-1.dsc
A       main/source/g/gnome-user-share/gnome-user-share_48.1-1.dsc
D       main/source/g/gnote/gnote_48.0-2.dsc
A       main/source/g/gnote/gnote_48.1-1.dsc
```
