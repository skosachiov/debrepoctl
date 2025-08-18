# debrepoctl

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
