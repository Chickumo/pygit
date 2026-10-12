# 1. Project Overview

PyGit is a local, single-user version-control system implemented entirely in Python's standard library. It records immutable file snapshots, stages changes independently of the working directory, maintains branches and a commit graph, compares revisions, restores files safely, merges divergent histories at file granularity, and verifies repository integrity.

The required deliverable is a runnable Python package, its automated black-box acceptance suite, and project documentation. The normative runtime is CPython 3.13 on Linux, Windows, or macOS with a local filesystem supporting ordinary files, directories, and exclusive file creation. All required behavior must work on at least one of those systems; platform-dependent acceptance cases must be marked explicitly. The format is platform-independent within the supported path rules. There are no third-party runtime, build, or test dependencies, external VCS processes, network operations, or installation requirements. Running the package from a source checkout must be sufficient.

This is a behavioral and data-format contract. Internal APIs, classes, data structures, traversal strategies, diff algorithms, merge-base discovery, and transaction mechanisms are deliberately unspecified. The project tree in section 4 is a suggested organization, not a prescribed implementation. Official Git manuals in section 7 provide terminology and conceptual background; this document defines PyGit's behavior whenever its formats, commands, or safety rules differ from Git.

**Required capabilities:** binary-exact snapshots represented by hierarchical directory trees; content-addressed, compressed objects; a persistent staging index; attached, detached, and unborn HEAD states; ordinary and two-parent commits; deterministic history and differences; safe branch switching and restoration; file-level three-way merges with explicit conflict resolution and abort; command-specific validation and comprehensive integrity checking; Unicode paths; process-level exclusion; and bounded handling of malformed input.

**Deliberate limitations:** no actual Git compatibility, remotes, tags, stash, rebase, cherry-pick, submodules, hooks, ignore patterns, rename detection, executable-bit tracking, permission/ownership/timestamp preservation, empty-directory tracking, symlink tracking, automatic text-conflict merging, octopus merges, recursive merge-base synthesis, garbage collection, or automatic crash recovery. A rename is a deletion plus an addition. All files, including dotfiles, are eligible except reserved repository metadata. Python source files have no special status. File-level merge rules apply equally to text and binary files.

Normal operations must be safe against ordinary errors and competing PyGit processes. Protection against a malicious process changing filesystem objects during a command, sudden power loss, permanent storage failure during rollback, and hostile network filesystems is outside the guarantee. A killed process can leave a lock or inconsistent repository; no command may silently guess a recovery. Offline recovery from a known-good copy is outside this CLI.

The contract requires support for at least 10,000 files per snapshot, 10,000 reachable commits, and individual files up to 64 MiB, subject to the exact limits in section 5. These are correctness targets, not prescribed complexity or timing targets. Completion means every applicable acceptance case in section 6 passes; there are no optional feature tiers.

# 2. CLI Specification

**Invocation and grammar**

The executable spelling throughout this document is **python -m pygit**. The package must be importable when invoked from a repository or any of its descendants; the test environment may supply the source checkout through Python's module search path.

Uppercase words in syntax tables are placeholders. Square brackets mean optional syntax; PATH... means one or more separate arguments. Alternatives shown on separate lines are exclusive forms. Angle-bracket identifiers in examples are explanatory substitutions, never literal accepted object IDs.

Options use their full spelling, except the explicitly specified -m, -d, and -h aliases. No option abbreviation is allowed. Repeated options, unknown options, incompatible forms, extra positional arguments, and missing required arguments are usage errors. Options may precede or follow positional arguments before --. A literal -- ends option processing. For commands accepting path operands, -- is optional unless needed to distinguish a path beginning with a hyphen; all examples use it for clarity. Shell expansion and quoting happen outside PyGit; PyGit itself performs no glob, environment-variable, or tilde expansion.

Long options taking values accept either a separate next argument or the form --option=value. Short options taking values require a separate next argument; combined short options and attached short-option values are unsupported. No subcommand at all is E_USAGE. init's DIRECTORY is a host-native relative or absolute directory argument, unlike repository PATH selectors; "." and ".." are allowed there, but no symlink/reparse-point traversal is allowed.

Except init and help/version, commands discover the nearest ancestor containing an entry named .pygit. That entry defines the candidate root even when malformed; a corrupt inner repository must not fall through to an outer repository. The root and current directory must be real directories. Symlinked directory ancestors in the supplied invocation path, and Windows junction/reparse-point equivalents, are unsupported.

If the discovered .pygit entry is not a real directory, every repository command, including fsck, returns the ordinary E_CORRUPT stderr error without trying to create a lock inside it. This container-safety check precedes the lock rule. A valid candidate directory with invalid contents can be locked and inspected by fsck.

REV accepts exactly HEAD, an existing branch name, or a full 64-character lowercase hexadecimal commit object ID. Abbreviated IDs, uppercase hexadecimal IDs, relative ancestry expressions, raw refs paths, and non-commit object IDs are rejected. HEAD or a branch without a commit is an unborn revision, not an empty commit. There is no revision parsing of filenames.

NAME is an ASCII branch name matching a letter followed by zero to 31 ASCII letters, digits, underscores, or hyphens. HEAD is reserved in any letter case. Branch names must be distinct under ASCII case folding. Refs store the original accepted spelling.

TIMESTAMP is a base-10 integer from 0 through 253402300799 inclusive, with no sign and no leading zero except the value 0. It represents whole UTC seconds since the Unix epoch. If omitted, use the current UTC time rounded down to seconds, once per commit-producing invocation. Timestamps do not control commit ordering or ancestry.

AUTHOR is a nonempty Unicode scalar-value string of at most 256 UTF-8 bytes, containing at least one non-whitespace character and no U+0000–U+001F or U+007F. MESSAGE is a Unicode scalar-value string of 1–4096 UTF-8 bytes containing at least one non-whitespace character and no U+0000; embedded newlines are allowed. Preserve both strings exactly, without trimming or normalization. AUTHOR is explicitly required; there is no implicit configuration or environment-variable author.

**Command table**

All common validation, locking, path, transaction, and corruption rules below apply in addition to the errors listed in this table.

| Command | Syntax after python -m pygit | Arguments and expected behavior | Relevant refusal conditions |
| --- | --- | --- | --- |
| Global help | --help or -h | Display all commands, accepted forms, and a brief description; exit 0 without repository discovery. | Additional arguments: E_USAGE. |
| Command help | COMMAND --help or COMMAND -h | Display that command's forms and options; exit 0 without repository discovery. Help is a standalone form. | Unknown command or additional arguments: E_USAGE. |
| Version | --version | Emit exactly "pygit 1" followed by LF; exit 0 without repository discovery. | Additional arguments: E_USAGE. |
| Initialize | init [DIRECTORY] | DIRECTORY defaults to the current directory and must already exist. Create a format-1 repository with unborn main and an empty index; preserve all existing working files. Output {"branch":"main","initialized":true}. | Existing .pygit entry: E_EXISTS. A repository marker in an ancestor of DIRECTORY: E_NESTED. Missing/non-directory target, link traversal, or unsupported target: E_PATH. |
| Inspect state | status | Report HEAD, merge state, staged changes, unstaged changes, and untracked regular files using the status schema below. | Unsupported/unreadable working entries or invalid paths within the scan: E_PATH or E_IO. |
| Stage | add -- PATH... | Replace selected index entries with current file bytes; stage tracked deletions; mark selected merge conflicts resolved. Output {"resolved":R,"staged":N}. Do not alter working files. | A selector with no eligible match: E_PATH. Invalid resultant snapshot: E_STRUCTURE. Unsupported file: E_PATH. Size limit: E_LIMIT. |
| Unstage | unstage -- PATH... | Replace selected index paths with their HEAD versions, or absence when HEAD is unborn. Working files remain untouched. Output {"unstaged":N}. | No matching path in HEAD/index: E_PATH. Any pending merge: E_STATE. Invalid resultant snapshot: E_STRUCTURE. |
| Remove | rm [--cached] [--force] -- PATH... | Select index entries or unresolved-conflict paths. Stage their absence and resolve their conflicts. Without --cached, also remove selected working regular files. Output {"removed":N,"resolved":R}; N counts removed index entries. | --cached and --force together: E_USAGE. No eligible match: E_PATH. Without --cached or --force, an existing working file different from its index version: E_DIRTY. A selected non-regular working node: E_PATH. |
| Commit | commit -m MESSAGE --author AUTHOR [--timestamp TIMESTAMP] [--allow-empty] | Create a snapshot from the index only. Its sole parent is current HEAD, or it has no parents when unborn. Advance the attached branch or detached HEAD. Output {"commit":OID}. | No index-versus-HEAD change without --allow-empty: E_EMPTY. Pending merge: E_STATE. Invalid metadata: E_ARGUMENT. |
| History | log [REV] [--all] [--max-count N] | Without REV, start at HEAD. --all instead starts at every branch tip and detached HEAD. Emit the history records specified below, once per reachable commit. N is a positive decimal integer, without leading zeros, at most 1000000000. | REV with --all: E_USAGE. Explicit unknown/unborn REV: E_REVISION. Invalid N: E_ARGUMENT. |
| List branches | branch | Output the branch-list schema below, including the conceptual current unborn branch if applicable. | Common repository errors only. |
| Create branch | branch NAME [REV] | Create NAME at REV, defaulting to HEAD. Do not switch or change index/worktree. Output {"branch":NAME,"target":OID}. | Name invalid: E_ARGUMENT. Existing/case-colliding branch: E_EXISTS. Unknown/unborn target: E_REVISION. Pending merge: E_STATE. |
| Delete branch | branch -d NAME | Delete a non-current branch only when its tip is an ancestor of, or equal to, current HEAD. Detached born HEAD is allowed for this check. Leave objects intact. Output {"deleted":NAME}. | Missing branch: E_REVISION. Current branch, unborn HEAD, or tip not reachable from HEAD: E_STATE. Pending merge: E_STATE. |
| Switch branch | switch NAME | Require clean tracked state; attach HEAD to the existing branch, replace index with its snapshot, and safely update working files. Output {"branch":NAME,"head":OID}. | Unknown/unborn branch: E_REVISION. Dirty tracked state: E_DIRTY. Untracked obstruction: E_COLLISION. Pending merge: E_STATE. |
| Detach | switch --detach REV | Require clean tracked state; set detached HEAD to REV and restore that snapshot. Output {"branch":null,"head":OID}. | Same safety errors as switch; unknown/unborn REV: E_REVISION. |
| Restore files | restore [--source REV] [--force] -- PATH... | Change selected working paths to their versions in REV, or in the current index if --source is absent. Source absence means removal. Do not change index, HEAD, or conflict-resolution state. Output {"restored":N}. | Unknown/unborn source: E_REVISION. No eligible path: E_PATH. Local changes without --force: E_DIRTY. Any untracked obstruction, even with --force: E_COLLISION. |
| Compare | diff [--staged] [-- PATH...] OR diff REV1 REV2 [-- PATH...] | Default: index versus tracked working state. --staged: HEAD snapshot versus index, treating unborn HEAD as empty. Two revisions: first snapshot versus second. Emit diff records below. | Only one REV, more than two REVs, or --staged with REVs: E_USAGE. Unknown/unborn explicit REV: E_REVISION. Unresolved conflicts for index/worktree comparisons: E_STATE. |
| Begin merge | merge REV -m MESSAGE --author AUTHOR [--timestamp TIMESTAMP] | Require attached, born HEAD and clean tracked state. Merge REV according to the merge contract below; metadata is retained if resolution is needed. Output result object below. | Pending merge/detached/unborn HEAD: E_STATE. Dirty: E_DIRTY. Unknown REV: E_REVISION. No common ancestor: E_UNRELATED. Multiple best bases: E_BASE. Unsupported structural combination: E_STRUCTURE. Obstruction: E_COLLISION. |
| Finish merge | merge --continue | Require a pending merge, no unresolved conflicts, and no unstaged changes under the merge-completion rule. Commit the index with the original two parents and saved metadata; remove merge state. Output {"commit":OID,"result":"merged"}. | No merge: E_STATE. Remaining conflicts: E_UNRESOLVED. Unstaged edits or missing staged files: E_DIRTY. |
| Abort merge | merge --abort | Require a pending merge. Restore pre-merge HEAD snapshot and index, remove merge state, and apply the explicit abort-discard policy below. Output {"result":"aborted"}. | No merge: E_STATE. Untracked structural obstruction or unsupported node: E_COLLISION or E_PATH. |
| Inspect object | cat-object [--raw] OID | OID is a full lowercase object ID of any type. Validate the requested object locally, without following its references. Default: output {"id":OID,"size":N,"type":TYPE}, where size is uncompressed payload bytes. --raw emits exactly the payload bytes, without header or added LF. | Bad ID syntax: E_ARGUMENT. Missing requested object: E_OBJECT. Invalid requested object or common metadata: E_CORRUPT. |
| Verify repository | fsck | Inspect all metadata and every stored object, including unreachable objects; report the integrity schema below. Never repair, delete, or reserialize anything. | Detected integrity errors: exit 3 with the report. Filesystem failure preventing inspection: E_IO. Existing lock: E_LOCKED. |

**Output, exit status, and error contract**

Except help, version, and cat-object --raw, stdout is UTF-8 canonical JSON as defined in section 5, with exactly one LF after each record and no byte-order mark. Empty log or diff output contains zero bytes. Successful mutations produce exactly their listed object. JSON examples with placeholder IDs describe shapes; actual commands always emit complete IDs. No color, progress messages, implicit pager, locale-dependent formatting, prompts, or successful-command stderr output is permitted.

Errors produce no stdout and exactly one stderr record with keys error and message: {"error":"E_PATH","message":"..."}. The code is normative. The message is implementation-selected, nonempty, and must identify the relevant argument, metadata item, or working path when one exists. Diagnostics must not expose file contents or print tracebacks for expected failures.

These output guarantees assume writable stdout/stderr. A broken output pipe or failed output device is E_IO when reporting remains possible; already-emitted bytes cannot be withdrawn, and an already-completed mutation need not be undone solely because its result could not be delivered. Filesystem transaction guarantees otherwise remain as specified. Tests of ordinary command failures use functioning output streams.

| Exit | Meaning |
| --- | --- |
| 0 | Success, including a diff showing differences, a no-op, or fsck with only unreachable objects. |
| 1 | Validly formed request refused: E_ARGUMENT, E_NOT_REPOSITORY, E_EXISTS, E_NESTED, E_PATH, E_STRUCTURE, E_LIMIT, E_REVISION, E_OBJECT, E_STATE, E_EMPTY, E_DIRTY, E_COLLISION, E_UNRELATED, E_BASE, or E_UNRESOLVED. |
| 2 | E_USAGE: command-line grammar error. |
| 3 | E_CORRUPT: invalid repository data; fsck instead emits its complete report on stdout and leaves stderr empty. |
| 4 | E_IO: permission, read/write, or recoverable filesystem failure. |
| 5 | E_LOCKED: repository lock already present. |
| 6 | A merge successfully entered the unresolved state; emit its conflict result on stdout, leave stderr empty, and preserve the specified merge changes. This is not rollback-triggering failure. |

Validate CLI grammar before repository discovery. An existing lock takes precedence over inspection of repository contents. Beyond those rules, a request containing multiple independent faults may report any applicable fault. Tests asserting a specific fault must isolate that fault.

**Paths, selectors, and scans**

CLI PATH operands are relative to the invocation directory, not necessarily the repository root. They use "/" as the only separator on every platform. Absolute paths, drive/UNC paths, backslashes, empty operands, any ".." component, and traversal through a symbolic link or reparse point are rejected. A leading "./", interior "." components, repeated "/", and a trailing "/" may be collapsed; the resulting root selector is ".". This lexical cleanup never changes case or Unicode normalization. Paths cannot escape the discovered root.

Stored paths and eligible working paths obey section 5's portable naming rules. A selector chooses its exact eligible file path plus eligible descendants separated by "/", independently of whether that selector currently exists as a directory. For example, selecting a deleted tracked directory selects its tracked descendants. Overlapping and repeated selectors count each path once. "." is always a valid selector and may select nothing; every other selector must select at least one eligible path. Selection is evaluated against the complete command input state before mutation.

Selection universes:

| Operation | Eligible paths |
| --- | --- |
| add | Regular working files, index paths, and unresolved-conflict paths. A missing indexed/conflicted file stages absence. An empty directory alone is not a match. |
| unstage | Union of HEAD snapshot and index paths. |
| rm | Union of index paths and unresolved-conflict paths; selecting a directory does not authorize removal of unrelated files in it. |
| restore | Union of source snapshot, HEAD snapshot, index paths, and unresolved-conflict paths. Working-only untracked files are never a selection source. |
| diff | Union of the two compared maps before filtering. "." remains valid when both are empty. |

Recursive working scans for add and status exclude only the root .pygit subtree. Another .pygit entry anywhere under the scanned scope denotes an unsupported nested repository and causes E_NESTED. Explicit selection of the root metadata path is E_PATH. Other reserved-name or unsupported-node encounters in scanned scope cause E_PATH; they are not silently skipped. A command confined to selected paths need not inspect unrelated untracked paths, except as required by restoration safety. Commands that do not inspect the working tree are not blocked merely by unrelated unsupported working nodes.

For add, individually valid names that collide only as members of the resulting snapshot give E_STRUCTURE. A portable-name collision within a status working scan gives E_PATH. Working entries must be checked for supported type before interpreting their contents or absence; a symlink or special node is never treated as a missing regular file.

A working directory at a path that is a tracked file is treated as absence of that file for status and diff; its regular descendants are separate paths. add must reject selecting a directory tree if the resulting index would retain both a file and its descendant. Deletions and additions selected together may make the resultant snapshot valid.

add, unstage, and rm report N as the number of distinct stage-zero path-to-blob mappings changed or removed, comparing absence as a value. R counts unresolved conflict records removed, even if the stage-zero mapping was already the chosen value. restore reports the number of selected regular-file paths whose bytes or presence changed; created or removed directories are not counted. A successful no-op reports zero. Reading a working file must capture one coherent byte sequence; concurrent external edits are outside the required contract.

**State and display contracts**

Let H be the HEAD snapshot, or the empty map when unborn; I be the stage-zero index; and W be regular working files. A path's value is its blob identity or absence. A committed snapshot is the full root-relative file map described by its root tree and all descendant trees; directory entries themselves are not file-map entries. Comparisons use bytes/content identities, never file size or modification time as proof of equality. The index is a complete prospective snapshot, stored as a flat file-path list.

status emits {"branch":NAME_OR_NULL,"entries":ARRAY,"head":OID_OR_NULL,"merge":MERGE_OR_NULL}. An attached unborn repository has branch "main" and head null. MERGE is {"base":OID,"ours":OID,"theirs":OID} while a merge is pending; otherwise null.

Each status entry has exactly index, path, and worktree. For a path in H or I, index compares H to I; worktree compares I to W. Each comparison yields " " for equal, "A" for absent-to-present, "D" for present-to-absent, or "M" for differing present contents. A working file absent from both H and I is "?" in both columns, unless unresolved. Unresolved conflict paths are always "U" in both columns, regardless of their working contents. Omit equal/equal entries. Sort entries by the UTF-8 bytes of their stored paths. Report one entry per file, never a directory summary. A staged deletion with the old file still on disk has index "D" and worktree "A"; it is not a separate untracked entry.

Tracked cleanliness means H equals I, no unresolved conflicts, and W equals I at every path in H or I. Unrelated untracked files do not make tracked state dirty. Creating an ordinary commit is allowed with unstaged or unrelated untracked changes; it always commits I.

branch emits {"branches":[{"current":BOOLEAN,"name":NAME,"target":OID_OR_NULL},...]}, sorted by ASCII branch name. Detached HEAD means all current flags are false. Only a current conceptual unborn branch has target null.

log emits one {"commit":COMMIT_PAYLOAD_OBJECT,"id":OID} record per reachable commit. An ancestor includes the commit itself and anything reachable through either parent recursively. A commit's generation is the maximum number of parent edges on a path from it to a root commit. Order records by descending generation, then ascending hexadecimal ID for equal generations. This orders children before parents even when timestamps run backwards. Deduplicate shared ancestors. --max-count applies to the final ordered stream. An implicit unborn HEAD and --all with no commits yield empty output; explicit log HEAD in an unborn repository is E_REVISION.

**Difference records**

Default diff compares I against W restricted to paths in H or I; genuinely untracked files are excluded. --staged compares H with I. During a pending merge, either form refuses while any conflicts remain, even if a path filter would exclude them. Two-revision diff remains available.

Emit one record per changed path, sorted by UTF-8 path bytes, with exactly change, edits, kind, new, old, and path. old/new are blob IDs or null for absence; computing an ID for working content does not store an object. change is "A", "D", or "M". Existence changes are changes even when the present file is empty.

A present file qualifies as text when its bytes decode as strict UTF-8, contain no U+0000, have at most 1 MiB, and contain at most 2,000 lines. Absence is an empty text sequence. If either present side fails those conditions, kind is "binary" and edits is null. Thus a large valid UTF-8 file may receive a binary summary. For text, kind is "text" and edits is an array of records with exactly op and text.

A text line ends at LF and includes that LF. A final nonempty suffix without LF is one line. An empty file has zero lines. CR has no special delimiter meaning and remains part of the text. Each edit record contains exactly one complete line from a side, with op equal, delete, or insert. The sequence must reproduce the old line sequence from equal/delete records and the new sequence from equal/insert records. Equal records require identical lines. Among all valid sequences, require the minimum total number of delete and insert records. If several minima exist, choose the lexicographically smallest operation sequence with operation ordering equal before delete before insert. This specifies the result, not an algorithm. Do not group adjacent records or omit equal lines.

**Restoration and deletion safety**

switch, restore, merge, and merge --abort must never follow links, write outside the root, or access .pygit as a tracked path. Validate every required object before any working-file change. An invalid target or obstruction anywhere rejects the whole command.

Switching requires tracked cleanliness even when switching to the already-current branch or detached commit. It replaces all tracked content and I with the target snapshot, removes formerly indexed files absent from the target, and preserves every unrelated untracked file byte-for-byte. Existing directories can contain target files. An untracked file at a destination, an untracked file blocking a needed directory, or an untracked descendant of a directory that must become a file is E_COLLISION, even when its bytes match the target. An empty directory may be replaced by a required file. A tracked file-to-directory or directory-to-file transition is allowed when every obstructing file belongs to the old tracked snapshot and the required removal is safe. Empty directories may remain after removals; their precise presence is not versioned.

restore changes only selected paths and necessary parent directories. For a selected path, its desired value comes from the source. Without --force, a content/presence change is permitted only when the existing working value equals I; a path already equal to the desired value is a no-op. Local modifications and local deletions otherwise require --force. --force authorizes discarding selected tracked bytes, not untracked bytes. A working regular file absent from both H and I and not an unresolved path is protected as untracked, even if a historical source has that path or its bytes already match. Working-only descendants and blocking ancestors are protected too. Unselected tracked files cannot be removed merely to satisfy a selected target. A structural change therefore requires selectors covering every affected tracked file. Pending-merge restore never resolves a conflict; add or rm must record the decision.

rm without --cached removes only selected files, never recursively deletes a selected directory as a unit. A missing working file is acceptable. Without --force, an existing file must equal its current index version; a conflict whose index value is absent therefore requires --force to remove an existing file. --cached changes the index and conflict records only, leaving even edited working files intact.

**Merge contract**

Begin-merge validation always checks supplied metadata, clean tracked state, an attached born HEAD, and a valid target, including no-op and fast-forward cases.

Let O be the original HEAD commit and T the requested target. If T is an ancestor of O, output {"result":"already-up-to-date"} and change nothing. Otherwise, if O is an ancestor of T, advance the current branch to T, set I and working tracked files to T's snapshot under switch safety, and output {"commit":T,"result":"fast-forward"}. Do not create a commit or pending-merge file in either case; supplied author/message/time do not rewrite the existing target.

For divergent histories, a common ancestor is a commit ancestral to both tips. A best common ancestor is one that is not a strict ancestor of another common ancestor. Require exactly one best common ancestor B. No common ancestor gives E_UNRELATED; more than one best base gives E_BASE. Do not choose a base using timestamp, object ID, branch order, or path similarity.

Consider the union of paths in B, O, and T. For divergent merges only, reject E_STRUCTURE if that union contains a file/directory prefix collision or two distinct path spellings whose complete paths or directory prefixes collide under the portable comparison in section 5. This deliberately excludes divergent file/directory and case-only structural merges. Ordinary fast-forward switching still supports safe file/directory transitions.

At each path, B, O, and T are blob IDs or absence. The required result is:

| Relationship between values | Result |
| --- | --- |
| O equals T | That shared value. |
| O differs from T and O equals B | T. |
| O differs from T and T equals B | O. |
| None of the preceding relationships holds | An unresolved conflict. |

These rules include additions and deletions. Distinct edits to different files can combine; distinct edits to the same file conflict even when they touch different text lines. Identical additions and identical modifications do not conflict.

For a conflict, retain O in stage zero and in the working tree, including absence when O is absent. Store the three original values in the index conflict record. Do not add conflict markers, rename files, or create sidecar copies. For non-conflicts, the result value enters I and the working tree.

Before a divergent merge, protect every untracked obstruction across the entire B/O/T path union, including a formerly tracked base path now absent in O; reject before changing anything. This preserves the later abort guarantee. On successful conflict-free divergence, create a two-parent commit with parents [O,T], even when its tree equals O's tree; advance the branch and leave no pending state. Output {"commit":OID,"result":"merged"}.

If there are conflicts, do not advance HEAD or its branch and do not create a merge commit. Persist MERGE.json and the conflict-bearing index; apply non-conflicting working changes and keep conflicted paths at O. Output {"conflicts":[PATH,...],"result":"conflicted"}, sorted by UTF-8 path bytes, and exit 6.

During a pending merge, allow status, diff, log, branch listing, cat-object, fsck, add, rm, restore, merge --continue, and merge --abort. Refuse commit, unstage, branch creation/deletion, switch, and another begin-merge with E_STATE. Help/version remain available. add and rm remove selected conflict records, even if the recorded choice equals O or absence. Files edited without add/rm remain unresolved. They may also stage additional ordinary changes.

merge --continue requires no conflict records and W equal to I at all paths in the union of the original managed paths and current I. An absent index value requires absence of a regular working file at that managed path. Unrelated untracked files are permitted. Create a two-parent commit [O,T] using the saved author, message, and timestamp; an unchanged tree is allowed. HEAD and the current branch must still identify O before continuation.

merge --abort is explicit authorization to discard all working edits at original managed paths, including conflict-resolution edits and modifications made after the merge began. Restore those paths to O, remove merge-introduced files absent from O, restore I exactly to O, and remove pending state. Files outside the original managed path set remain byte-identical, including files newly staged during resolution; such files become untracked if absent from O. If a protected outside file blocks an original managed path, refuse the entire abort. HEAD and its branch remain at O. No object is garbage-collected.

**Sample terminal interactions**

These examples show only shell interactions and specified data, not implementation. Working files are created with a text editor unless a shell action is stated. In the displays, <C1>, <C2>, <B1>, and <B2> stand for full returned IDs and must be substituted in actual commands.

A fresh directory contains note.txt with the exact UTF-8 bytes "alpha\n":

~~~text
$ python -m pygit init
{"branch":"main","initialized":true}
$ python -m pygit status
{"branch":"main","entries":[{"index":"?","path":"note.txt","worktree":"?"}],"head":null,"merge":null}
$ python -m pygit add -- note.txt
{"resolved":0,"staged":1}
$ python -m pygit commit -m "Initial snapshot" --author "Ujjwal" --timestamp 1700000000
{"commit":"<C1>"}
$ python -m pygit status
{"branch":"main","entries":[],"head":"<C1>","merge":null}
$ python -m pygit branch feature
{"branch":"feature","target":"<C1>"}
$ python -m pygit switch feature
{"branch":"feature","head":"<C1>"}
~~~

Change note.txt to the exact bytes "beta\n":

~~~text
$ python -m pygit diff
{"change":"M","edits":[{"op":"delete","text":"alpha\n"},{"op":"insert","text":"beta\n"}],"kind":"text","new":"<B2>","old":"<B1>","path":"note.txt"}
$ python -m pygit add -- note.txt
{"resolved":0,"staged":1}
$ python -m pygit commit -m "Change note" --author "Ujjwal" --timestamp 1700000001
{"commit":"<C2>"}
$ python -m pygit switch main
{"branch":"main","head":"<C1>"}
$ python -m pygit merge feature -m "Integrate feature" --author "Ujjwal" --timestamp 1700000002
{"commit":"<C2>","result":"fast-forward"}
~~~

Change note.txt locally to "unsaved\n". Diagnostic message wording is illustrative:

~~~text
$ python -m pygit restore -- note.txt
{"error":"E_DIRTY","message":"Local changes would be overwritten: note.txt"}
$ python -m pygit restore --force -- note.txt
{"restored":1}
$ python -m pygit status
{"branch":"main","entries":[],"head":"<C2>","merge":null}
~~~

The first command's JSON is on stderr, its exit status is 1, and its stdout is empty. The other commands succeed. note.txt finally contains "beta\n".

# 4. Project Directory Structure

This is the software source tree, separate from any repository being versioned. Filenames and module boundaries may change without changing the external contract.

~~~text
pygit-project/
├── README.md                    — Runtime setup, invocation, supported limits, and user-facing command reference.
├── FORMAT.md                    — Exact implemented format contract and format-version policy.
├── pygit/
│   ├── __init__.py              — Package identity and public package metadata.
│   ├── __main__.py              — Module-execution entry point.
│   ├── cli.py                  — Argument grammar, dispatch, and exit-status translation.
│   ├── errors.py               — Domain failure categories and diagnostic information.
│   ├── repository.py           — Repository discovery and repository-wide invariants.
│   ├── paths.py                — Path identities, selectors, portability, and containment rules.
│   ├── serialization.py        — Canonical JSON and data-schema validation.
│   ├── objects.py              — Object envelopes, identities, compression, and immutable storage.
│   ├── snapshots.py            — Hierarchical tree values, complete file maps, and structural validity.
│   ├── index.py                — Stage-zero index and unresolved-conflict persistence.
│   ├── refs.py                 — HEAD, branch identities, and reference validation.
│   ├── history.py              — Commit graph semantics, ordering, and ancestry queries.
│   ├── worktree.py             — Working-file inspection and safe restoration behavior.
│   ├── staging.py              — Add, remove, and unstage command semantics.
│   ├── commits.py              — Commit creation and commit metadata rules.
│   ├── differences.py          — Deterministic text edit records and binary summaries.
│   ├── merging.py              — Merge results, conflict lifecycle, and abort semantics.
│   ├── integrity.py            — Command-specific validation scopes and comprehensive fsck reporting.
│   ├── transactions.py         — Command isolation and ordinary-failure state guarantees.
│   └── output.py               — Stable terminal serialization and raw-object output.
└── tests/
    ├── __init__.py              — Standard-library test discovery support.
    ├── support.py              — Isolated CLI test environments and observable-state assertions.
    ├── fixtures/               — Documented static binary, Unicode, and malformed-format samples.
    ├── test_cli.py             — Grammar, output, exit codes, and repository discovery cases.
    ├── test_storage.py         — Hierarchical tree, object-format, and metadata-conformance cases.
    ├── test_staging.py         — Index independence, selection, deletion, and status cases.
    ├── test_history.py         — Branch, detached-state, and graph-order cases.
    ├── test_diff.py            — Text minimality, tie-breaking, and binary-diff cases.
    ├── test_restore.py         — Restoration, obstruction, and byte-preservation cases.
    ├── test_merge.py           — Merge outcomes, resolution, continuation, and abort cases.
    ├── test_integrity.py       — Corruption, limits, locking, and ordinary-failure cases.
    └── test_end_to_end.py      — The complete acceptance scenario.
~~~

# 5. Storage and Data Format Specification

**Repository layout**

All named metadata files below are required except a branch file that is legally unborn, MERGE.json when no merge is pending, and LOCK when no command owns the lock. Required directories exist even when empty. No unspecified persistent files are permitted under .pygit.

~~~text
working-root/
└── .pygit/
    ├── FORMAT                  — Exact ASCII format marker.
    ├── HEAD                    — Symbolic reference or detached commit ID.
    ├── index.json              — Complete staged snapshot and unresolved conflicts.
    ├── MERGE.json              — Present only during a pending divergent merge.
    ├── LOCK                    — Present only during a repository operation or after interruption.
    ├── refs/
    │   └── heads/
    │       └── NAME            — One branch's commit ID.
    ├── objects/
    │   └── hh/
    │       └── remainder       — Compressed object; first two ID hex digits are hh.
    └── tmp/                    — Private transient workspace; empty while idle.
~~~

FORMAT contains exactly the 15 ASCII bytes represented by "pygit-format 1\n". No BOM, CRLF, spaces after 1, or extra records are allowed. A missing or different marker is E_CORRUPT; no automatic upgrade occurs.

All metadata directories must be real directories, and metadata files and object files must be regular files. Symlinks/reparse points anywhere inside .pygit are invalid. Entries under refs/heads must be valid branch files, not directories. Object fan-out directories have exactly two lowercase hexadecimal characters; object basenames have exactly 62. Empty valid fan-out directories are permitted. Unexpected files/directories, invalid branch spellings, wrong metadata types, and idle tmp contents are corruption. Detection by ordinary commands is governed by the validation scopes below; fsck inspects the entire layout. LOCK is handled separately by the lock contract.

**Canonical JSON, called CJSON**

This exact representation applies to tree/commit payloads, index.json, MERGE.json, and JSON terminal output:

- UTF-8, without BOM. Strings contain Unicode scalar values; reject unpaired surrogates and invalid UTF-8.
- Object keys are unique strings, sorted in ascending Unicode code-point order. There are no duplicate keys.
- No insignificant whitespace: "," and ":" have no adjacent spaces; there is no indentation.
- Strings escape quotation mark as \", backslash as \\, and backspace, form feed, LF, CR, and tab as \b, \f, \n, \r, and \t respectively. Other U+0000–U+001F characters use exactly four lowercase hexadecimal digits after \u. All other scalar values, including non-ASCII characters and "/", appear literally.
- Integers use ordinary base-10 notation, without plus signs, leading zeros, or negative zero. Numeric fields in repository schemas below are nonnegative integers; booleans are not integers for schema purposes.
- null, true, and false use those exact lowercase spellings where the schema permits them. Floats, NaN, and infinities are never permitted.
- Arrays preserve their specified ordering. Reject unknown fields, missing fields, wrong types, and any noncanonical byte encoding.
- Object payload CJSON has **no terminating LF**. index.json and MERGE.json each contain CJSON followed by **exactly one LF**. Each terminal JSON record also has exactly one trailing LF. Those terminal/file framing LFs are not part of CJSON.

All metadata readers must detect duplicate JSON keys and exact schema violations; accepting a parser's default behavior is not a substitute for satisfying this contract. No metadata or object is executable input. Arbitrary-object deserialization and repository-driven code loading are prohibited.

**Path identity and portable validity**

A stored file path is a nonempty NFC-normalized Unicode scalar-value string, relative to the repository root, with "/" separators and no leading/trailing separator, empty component, "." component, or ".." component. No automatic Unicode normalization is performed when accepting a working path: non-NFC names are rejected. Author/message strings do not share this path normalization requirement.

Each component has 1–255 UTF-8 bytes. A complete stored path has at most 4096 UTF-8 bytes and at most 128 components. A component may not contain U+0000–U+001F, U+007F, backslash, colon, quotation mark, "<", ">", "|", "?", or "*"; it may not end with a space or dot. A component case-insensitively equal to .pygit is reserved at every depth. Within a component, the substring before its first dot may not equal CON, PRN, AUX, NUL, COM1 through COM9, or LPT1 through LPT9 under ASCII case folding. This is PyGit's fixed reserved-name set; it does not claim to enumerate every restriction of every filesystem.

Define a component's portable comparison key as its Unicode casefold result normalized to NFC. Two distinct component spellings with the same key cannot coexist at the same logical parent, including implicit directory components. Thus "Dir/a" and "dir/b" conflict even though their complete filenames differ. Exact duplicate paths and any file path that is a proper component-prefix of another file path are also invalid. Apply these rules to each tree, stage-zero index, applicable working scan, and the explicitly specified cross-snapshot merge union.

Path ordering always compares the unsigned UTF-8 bytes of the original accepted stored paths, not their comparison keys. Never translate stored separators to backslashes. At the filesystem boundary, the host must represent each chosen path exactly; an unrepresentable path or an unexpected name alias gives E_PATH on working operations. Other host restrictions remain legitimate E_PATH/E_IO failures, without rewriting names.

Only file contents and paths are versioned. Hard-linked working files may be read as ordinary files, but later PyGit restoration/removal must not change bytes through another name outside the selected change set. Link relationships themselves are not retained. Empty files are blobs with zero-byte payloads. Empty working directories are omitted from snapshots; only the root of an empty snapshot may use an empty tree.

**Object identity and envelope**

An object type is exactly one of the ASCII words blob, tree, or commit. Let P be its payload bytes and L be P's byte length.

The uncompressed object bytes are the concatenation of: the ASCII type; one ASCII space; the ASCII decimal representation of L; one NUL byte (00 hexadecimal); and exactly P. The decimal length has no sign or leading zeros, except 0 itself. No trailing bytes are allowed beyond the declared payload.

The object ID is the lowercase 64-character hexadecimal SHA-256 digest of that entire uncompressed envelope, including type, space, decimal byte length, NUL, and payload. It is **not** the digest of the payload alone, the compressed file, the path, the filename, or filesystem metadata. Hash length is bytes, not Unicode characters.

The physical path is .pygit/objects/ followed by the ID's first two characters as a directory and remaining 62 as a filename. One ID has one object path. Identical envelopes always reuse that path across files, commits, branches, and repeated staging. Never overwrite a pre-existing different/corrupt object at that path. A valid existing object must have the identical uncompressed envelope; any mismatch is E_CORRUPT.

An object file contains exactly one complete zlib-wrapped DEFLATE stream representing the entire envelope. No gzip/raw-DEFLATE wrapper, preset dictionary, concatenated streams, trailing junk, or truncated stream is permitted. Writers use compression level 6. Compressed byte-for-byte identity across zlib versions is not required, and valid readers accept any zlib compression level without a preset dictionary. Object identity depends only on uncompressed bytes.

A read is valid only if decompression completes, limits are respected, the header and declared size are exact, the ID matches the storage name/requested ID, the payload satisfies its type's schema, and every reference required by that command has the right type and exists. Never trust a claimed size before enforcing the independent limits.

**Object payload schemas**

A blob payload is exactly the original file bytes. No encoding detection, newline conversion, normalization, BOM removal, compression-specific interpretation, or file-mode field is applied.

A tree payload is CJSON with exactly entries and version:

~~~json
{"entries":[],"version":1}
~~~

Each tree represents exactly one directory. Every entries element has exactly name, oid, and type:

| Field | Required value |
| --- | --- |
| name | Exactly one valid stored-path component: nonempty NFC, no "/", and all component restrictions above. It is relative to this directory. |
| oid | Full lowercase 64-character object ID. |
| type | Exactly "blob" for a regular file or "tree" for a child directory. The referenced object's actual type must match. |

Entries are strictly sorted by the unsigned UTF-8 bytes of name, regardless of type. A directory cannot contain two entries with the same name or portable comparison key, even when their types differ. Every referenced object must exist. Tree payloads contain no absolute/root-relative prefix, parent pointer, file mode, timestamp, or flattened descendant list.

A commit's tree field identifies its root directory tree. A file's full stored path consists of its successive directory entry names and final blob entry name, separated by "/". That full path must satisfy the 4096-byte and 128-component limits. The expanded file map must satisfy all snapshot path and file-count rules. Directory objects do not appear in the index, status, or diff as tracked files.

Every referenced child tree must contain at least one entry, and every directory in a valid snapshot must ultimately contain a file. An empty root tree is valid and represents an empty snapshot. An empty tree stored without a referring commit is also a valid unreachable object. A parent entry referencing that empty tree as a child directory is invalid.

The tree-reference graph must be acyclic. Sharing is allowed: different directory names and different commits may reference the same tree ID. Identical directory contents, names, and child object IDs give identical tree payloads regardless of the directory's own location. Shared subtrees therefore occupy one physical object but contribute their files separately at each placement in an expanded snapshot. File counts, path lengths, and depth limits apply to those logical placements, not just distinct object IDs.

Each valid complete file map has one canonical hierarchical representation under these rules. Objects for unchanged or identical subdirectories must be reused by identity. Any case described elsewhere as a snapshot's "tree" means its root tree together with its descendant directory trees and blobs.

A commit payload is CJSON with exactly author, message, parents, timestamp, tree, and version. Field meanings:

| Field | Required value |
| --- | --- |
| author | AUTHOR string from the CLI contract. |
| message | MESSAGE string from the CLI contract. |
| parents | Array of zero, one, or two distinct full commit IDs; order is significant. |
| timestamp | Integer UTC timestamp in the specified range. |
| tree | Full ID of the root directory tree; its complete descendant structure represents the committed snapshot. |
| version | Integer 1. |

A root commit has no parents. Ordinary commits have one parent unless HEAD was unborn. Divergent merge commits have two parents: original current tip first, merged tip second. Commit records contain no cached branch name, mutable counter, generation number, filesystem timestamp, nonce, or redundant file data. Parent timestamps may be earlier, equal, or later than a child's timestamp.

The commit graph must be acyclic; every parent must exist and be a commit. Tree and blob references must have the specified types. There is no requirement that all valid stored commits be currently reachable. Independently constructed repositories with identical snapshots, parent IDs, author, message, and timestamp must produce identical commit IDs.

**Index**

index.json is CJSON with exactly conflicts, entries, and version, followed by LF:

~~~json
{"conflicts":[],"entries":[],"version":1}
~~~

Each index entries element has exactly oid and path. oid is a full lowercase blob ID; path is a complete valid root-relative file path. Entries are strictly sorted by path's UTF-8 bytes. Duplicate paths, portable aliases at any component, and file/directory prefix conflicts are invalid. Every referenced object must exist with type blob. This flat index schema deliberately differs from a directory tree's name/oid/type schema. It describes all staged files, including unchanged ones. Absence from entries is absence in the next snapshot; there are no directory entries, deletion tombstones, file modes, stat caches, or modification-time fields.

conflicts is sorted by path's UTF-8 bytes. Each record has exactly base, ours, path, and theirs. Its three values are blob IDs or null for absence. Each path appears at most once and must obey the stored-path rules. Records must correspond to genuine conflicts under the merge table using the active merge's base/ours/theirs snapshots. While unresolved, its stage-zero value must equal ours. Any non-null conflict blob must exist with type blob. A resolved path has no conflict record; its stage-zero value may reflect any valid user choice.

If MERGE.json is absent, conflicts must be empty. During a pending merge, the index may contain zero conflicts after resolution; it is still a pending merge until continue or abort. A commit command never implicitly finishes it.

**HEAD and branches**

A symbolic HEAD file is exactly ASCII "ref: refs/heads/NAME\n", with one space after the colon. A detached HEAD file is exactly a full lowercase commit ID followed by LF. No extra whitespace or lines are accepted.

A branch file .pygit/refs/heads/NAME contains exactly a full lowercase commit ID and LF. It must point to a commit, not a tree/blob. A zero-length file, "null", all-zero placeholder, or missing target object is invalid.

init writes symbolic HEAD for main and does **not** create a main branch file. A missing symbolic target is permitted only for refs/heads/main, making HEAD unborn. This exception applies only while HEAD actually names that missing ref. A non-current absent main is simply not an existing branch. Any other missing symbolic target is corruption. An actual branch file is never unborn.

Creating a branch named main while it is the current conceptual unborn branch is E_EXISTS. First commit creates its main ref. Branch creation at a valid explicit commit is possible even while current HEAD is unborn. Switching away from conceptual unborn main removes that conceptual listing; it does not create an empty ref.

An attached commit updates only the current branch file; detached commit updates only HEAD. Other branches remain byte-identical. Branch deletion never deletes objects. Full commit IDs can resolve valid unreachable commits.

Successful init creates no objects. Successful add may create only blobs for selected present working files. Ordinary commit and a completed merge may create only the root tree, descendant directory trees, and commit required for their result; all referenced blobs already exist. Only previously absent object IDs add physical objects. A pending conflicted merge creates no objects. All other successful commands create no objects. Existing objects are never deleted. These rules make deduplication and object-count observations precise; the ordinary-failure allowance for valid unreachable objects still applies.

**Pending merge**

MERGE.json is CJSON plus LF with exactly author, base, managed, message, ours, theirs, timestamp, and version. version is 1; author/message/timestamp retain the validated begin-merge inputs; base/ours/theirs are full commit IDs.

managed is the exact sorted union of file paths from those three snapshots. It has no duplicates and cannot change during resolution. The three commits must describe a divergent merge with the unique best base specified by base and a structurally valid union. At least one conflict must have existed when this pending merge began; zero current conflict records is allowed after resolution. HEAD must be symbolic, its branch must still point to ours, and its index must satisfy the pending-merge index rules. Snapshot references and all their reachable history must remain valid.

No separate original-index backup is needed in the format: the precondition requires it to equal ours. All original managed working content also equaled ours before the merge. Newly staged outside files do not enlarge managed.

**Limits**

MiB means 1,048,576 bytes. Limits apply equally to writers, readers, and malformed data.

| Item | Maximum |
| --- | --- |
| Blob payload | 64 MiB. |
| Tree or commit payload | 8 MiB. |
| index.json or MERGE.json, including framing LF | 8 MiB each. |
| Object file on disk | 65 MiB. |
| Uncompressed envelope | Applicable payload limit plus 32 header bytes. |
| Immediate entries in any one directory tree | 10,000. |
| File entries in any expanded snapshot or index | 10,000. |
| Conflict records in an index | 10,000. |
| Paths in managed | 30,000, subject to its file-size limit. |
| Object records stored | 100,000. |
| Commits reachable from all repository roots together | 10,000. |
| Branches, including conceptual unborn current branch | 1,000. |
| Object header before NUL | 31 bytes. |

A well-formed user operation exceeding a limit fails E_LIMIT without logical change. Pre-existing stored data exceeding a format limit is E_CORRUPT when it is within the command's validation scope. No size limit authorizes silent truncation. The text-diff threshold in section 2 chooses summary behavior and is not a rejection limit. Help output and diagnostic strings need not obey metadata-size limits.

Quota checks are explicit dependencies. A command that will create any new object must inventory object-store names and entry types, without opening unrelated object contents, and require the resulting physical object count to remain within 100,000. This inventory also detects malformed object-store layout. A command that will change a branch, detached HEAD, or the set of active merge roots must check the resulting combined ancestor history of all branch tips, detached HEAD, and active merge commits against the 10,000-commit limit. This quota check reads commit records and parent edges only, never the historical snapshots. Branch creation additionally checks the resulting branch count and name uniqueness. fsck checks all quotas globally.

An explicit history request for a valid unreachable commit may inspect at most 10,000 distinct commits in that requested ancestor graph; a larger requested graph gives E_LIMIT. This operation limit does not make a collection of otherwise valid unreachable objects corrupt unless a stored-format or repository-root quota is also violated.

**Validation, exclusion, and transactions**

Every repository command takes exclusive ownership for its entire operation, including read-only commands. While owned, LOCK contains exactly the ASCII bytes "pygit-lock-v1\n". If any LOCK entry already exists, immediately return E_LOCKED without altering it, examining ownership, waiting indefinitely, or deleting it. Two competing operations cannot both own the same repository. Read-only commands remove only their own transient lock on ordinary completion and do not otherwise change repository content.

init also must not overwrite or interleave with another initialization; competing initializations have at most one success. No persistent incomplete repository may be presented as a successful initialization.

Validation has three precise levels:

| Level | Required checks |
| --- | --- |
| Local object | Physical path/type, compressed stream, envelope, length limits, digest, canonical payload, exact fields/types, and immediate schema rules. Referenced IDs must be syntactically valid, but their objects are not followed. For a tree, this includes entry-name validity/order/uniqueness; for a commit, parent-array and metadata validity. |
| Snapshot | Local validation of a commit and its root tree, all descendant trees, and every referenced blob. Validate entry target types, absence of tree cycles/empty child trees, and the complete expanded path/file-count rules. Do not follow the commit's parents. For a directly requested tree snapshot, treat that tree as the root. |
| Ancestor history | Local validation of the starting commit or commits and every commit reached through parents, including parent types, missing parents, cycles, and applicable history limits. Do not open their root trees or blobs. |

Each ordinary repository command first validates **common metadata**: the real .pygit container; its allowed immediate children and required fixed directories; FORMAT; HEAD; index.json's complete local schema; optional MERGE.json's complete local schema; absence of idle tmp contents; and the current branch file when HEAD is attached. If HEAD is born, locally validate its target commit. The index's blob references are checked only as required below, not merely because index.json was parsed. The current unborn-main exception remains valid.

Checking fixed directories includes objects, refs, refs/heads, and tmp themselves; it does not require visiting object fan-out directories or unrelated branch files. The refs directory may contain only heads. An operation reading or writing any deeper path must validate its traversed directories and final entry types without following links. Branch listing and operations needing a branch inventory check branch filenames, case-folded uniqueness, raw ref-file syntax, and the branch-count limit. A directly resolved branch always requires a locally valid target commit.

An unknown explicit branch/revision is E_REVISION. A directly supplied full object ID that is absent or names a non-commit is E_REVISION when used as REV. A stored branch/HEAD target that is missing or not a commit is E_CORRUPT. A missing object requested directly by cat-object is E_OBJECT; a missing or wrong-type reference encountered within a required snapshot/history is E_CORRUPT.

The following scopes are additional to common metadata, quota checks, and pending-merge checks. "Index blobs" includes every non-null conflict value when the scope says all index blobs. Scope selection uses the pre-command state; a command must not silently overwrite an invalid object it is required to check.

| Command | Additional required object/reference scope |
| --- | --- |
| status | HEAD snapshot if born; all index blobs. |
| add | Old index blob for every selected indexed path; every selected conflict value; every object ID reused or newly published for selected working bytes. It does not need HEAD's ancestor history or unrelated index blob contents. |
| unstage | HEAD snapshot if born; old index blobs for selected indexed paths. |
| rm | Old index blobs and conflict values for selected paths, including --cached. |
| commit | HEAD snapshot if born; all index blobs; result's hierarchical snapshot and new commit; resulting repository history quota. |
| log | Ancestor history of the requested starting points, including before --max-count truncation. Referenced snapshots are outside scope. --all includes every branch tip and detached HEAD. |
| branch listing | Branch inventory and local validation of each listed tip commit; no ancestor histories or snapshots. |
| branch creation | Branch inventory; local target commit; resulting repository history quota. |
| branch deletion | Branch inventory; ancestor histories of HEAD and the selected branch tip for deletion safety; resulting repository history quota. |
| switch, including --detach | HEAD snapshot if born; all index blobs; target snapshot; resulting repository history quota. |
| restore | HEAD snapshot if born; all index blobs; the whole source snapshot when --source is supplied. Target snapshot validation covers unselected source files too, so a corrupt restore source cannot be partly used. |
| diff, default or --staged | HEAD snapshot if born; all index blobs; applicable tracked working files for default diff. |
| diff with two REVs | Both complete snapshots; no ancestor histories. |
| merge REV | Ancestor histories of ours and theirs; both snapshots; unique base snapshot for a divergent merge; all index blobs; any resulting snapshot/commit and resulting repository history quota. |
| merge --continue | Active merge's ancestor histories sufficient to verify its base and divergent relationship; all index blobs; new snapshot/commit and resulting repository history quota. |
| merge --abort | Active merge snapshots and the restored original snapshot; resulting repository history quota. Unrelated newly staged blob payloads are outside scope because abort discards their index entries while preserving their working files. |
| cat-object | Local validation of the requested object only, in addition to common metadata. A locally valid tree/commit may be inspected even when a referenced descendant/parent is broken. |
| fsck | Entire layout, all metadata, all stored objects and referenced relationships, all tree expansions and commit graphs, all quotas, and complete pending-merge invariants. |

For an otherwise allowed ordinary command while a merge is pending, additionally validate the base/ours/theirs snapshots. Check that HEAD is attached at ours, managed equals their exact file-path union, the union is structurally valid, at least one initial conflict exists under those three snapshots, and each remaining conflict record and its stage-zero value agree with them. The stronger claim that base is the unique best common ancestor is verified when beginning or continuing the merge and by fsck; it is not a reason for status or branch listing to scan history on every invocation.

Within the declared scopes, every required object must be fully validated before success or publication. Malformed object contents outside those scopes must not make an otherwise valid command fail. An additional quota or pending-merge dependency is part of the scope, as explicitly stated above. A valid command may therefore succeed while fsck reports damage to an old snapshot or an unrelated branch. This distinction never authorizes automatic repair, data replacement, or acceptance of corruption in the data that command does require.

All input validation, object verification needed by a mutation, and obstruction checking must be satisfied before externally visible logical changes. On an ordinary reported failure, HEAD, refs, index, merge state, and working file bytes/presence must equal their pre-command values. This covers multi-path commands, not just one file. A successful merge conflict (exit 6) is the explicitly specified exception.

Commands may leave newly created, valid, unreachable immutable objects after a reported failure; they may not overwrite old objects, publish broken refs, leave a partial index, leave their own lock, or leave temporary files. Empty working directories created during a rolled-back operation may remain, since empty directories are unversioned. A process still running after an injected one-time I/O failure must satisfy the same rollback guarantees when subsequent rollback I/O succeeds.

Abrupt termination and rollback prevented by persistent hardware/permission failure are outside the rollback guarantee. Such a command must never claim success; if it can still report an error, use E_IO. No automatic stale-lock clearing or recovery command is provided.

**Integrity report**

fsck validates every stored object independently, then metadata/reference relationships, reachable graph limits, cycles, and pending-merge invariants. It includes orphaned objects in schema, size, digest, and reference validation. It validates every stored tree's expansion considered as a root, and every commit's rooted expansion; invalid placements such as an empty child tree or an excessive prefixed path are errors on the referring tree or snapshot. This applies to unreachable trees too. Reuse of a valid subtree under multiple parents is not a cycle. It treats reachability roots as every actual branch tip, detached HEAD, stage-zero blob IDs, and active merge's three commit IDs plus conflict blob IDs. A conceptual unborn branch contributes no object.

An object is reachable when it is a root or can be followed from a root through a commit's root tree/parents or a tree's child trees/blobs. Report every locally valid stored object outside that closure as unreachable, including unreferenced trees and blobs, not just commits. Count a physically shared subtree once for reachability and object totals. Unreachable validity is not corruption and never triggers deletion.

The single stdout report has exactly errors, objects, and unreachable. objects has exactly blob, commit, and tree counts. Count objects whose own envelope, digest, payload, and local schema are valid, even if one of their references is missing/wrong-type. Do not count an invalid envelope or locally invalid payload. unreachable is sorted by full ID; include only locally valid objects. Reachability calculations follow valid references that can be read, and stop at invalid/missing endpoints.

Each errors entry has exactly code, message, and path. code is always "E_CORRUPT"; message is diagnostic prose identifying the violation. path is a forward-slash root-relative metadata/object path, or ".pygit" for a whole-repository invariant. Sort by UTF-8 path bytes, then message. Report at least one error for every independently detectable invalid file or invalid stored reference; suppressing redundant downstream complaints about the same missing object is permitted. Never invent successful counts for unreadable files. Filesystem I/O that prevents a full report instead uses the ordinary E_IO error contract.

A valid empty repository reports exactly:

~~~json
{"errors":[],"objects":{"blob":0,"commit":0,"tree":0},"unreachable":[]}
~~~

A report with errors exits 3, otherwise 0. Repository discovery and lock errors still use the ordinary stderr error contract.

# 6. Acceptance Tests

**Test conventions**

Every case runs in an isolated repository unless it explicitly continues a preceding state. All commands below have the prefix python -m pygit, omitted in compact table cells only. C0, C1, C2, O, T, M, and similar names denote full returned commit IDs; BLOB denotes a full blob ID observed in a raw tree/index or independently verified fixture. Substitute these symbols before invocation. Revisions described as branch names are literal branch names.

Unless stated otherwise, fixture commits use author "Tester", a nonempty distinct message, and explicit integer timestamps. A fixture may be constructed through the public CLI or supplied as static format-conforming repository bytes; tests must not depend on the implementation's internal functions, classes, caches, or module organization. Malformed fixtures are copies of otherwise valid repositories with the single described fault. Metadata/object-file inspection is an observable interface because section 5 specifies that format. Controlled filesystem test doubles are permitted under the explicit failure-testing contract below; they do not change the required CLI or authorize testing private PyGit interfaces.

For every command, check exit status and the correct output channel, field set, canonical encoding, and LF framing. Every expected refusal must also check that HEAD, refs, index, merge state, and all working file bytes/presence are unchanged. Ignore only the explicitly allowed extra valid unreachable objects and empty directories after rollback. Never ignore a leaked lock or temporary file. Variable diagnostic prose must satisfy the error contract but need not match an English sentence exactly.

The symbols "\n", "\r", "\t", and hexadecimal byte strings in test descriptions denote actual bytes/characters, not literal backslash text, unless stated otherwise. "Clean" means an empty status entries array with no pending merge. Assertions about working bytes compare complete bytes, not displayed text.

**CLI, discovery, and initial state**

| ID | Initial conditions | Commands or actions | Expected observable results |
| --- | --- | --- | --- |
| A01 | Existing directory with ordinary files and no repository. | init; status; branch; log; fsck. | Files unchanged; unborn main; every regular file untracked; branch target null; implicit log empty; fsck counts all zero with no errors/unreachable IDs; exact initial metadata from section 5. |
| A02 | Existing initialized directory. | init again. | E_EXISTS; no reset of index, refs, or objects. |
| A03 | No repository in the current directory or ancestors. | status; separately --help, status --help, --version. | status gives E_NOT_REPOSITORY; help/version succeed and create no files. Version bytes are exact. |
| A04 | Repository with subdirectory src/deep and file src/deep/a.txt. | From src/deep: add -- ./a.txt; status. | Stored path is src/deep/a.txt; status uses root-relative paths. No second repository is created. |
| A05 | Valid outer repository; its child directory contains an invalid .pygit entry. | From that child: status. Separately, attempt init in a normal child of the outer repository. | Inner candidate produces E_CORRUPT, without outer fallback; nested initialization gives E_NESTED. |
| A06 | Any directory. | Unknown command; add without paths; diff HEAD; commit without --author; diff --staged HEAD HEAD; repeated --author; abbreviated --auth; --help with extra arguments. | Each is E_USAGE, exit 2, without repository mutation. |
| A07 | Valid repository. | Commit with whitespace-only message, NUL in a supplied message, invalid author, --timestamp -1, --timestamp 01; log --max-count 0. | Each syntactically present but invalid value gives E_ARGUMENT, exit 1. A shell unable to pass NUL may use the static schema fixture equivalent for that subcase. |
| A08 | Unborn repository. | log HEAD; branch new; switch main; commit -m Empty --author Tester --timestamp 1; then repeat commit with --allow-empty. | First three give E_REVISION; ordinary empty commit gives E_EMPTY; allowed empty commit creates a root, empty tree, and main ref. Its tree equals the empty-tree vector below. |
| A09 | Valid repository with file -draft.txt and another file whose name contains a space. | add -- -draft.txt "two words.txt"; inspect status and raw tree after commit. | Literal paths are staged, reported, and stored exactly, without splitting, globbing, or option confusion. |
| A10 | Repository with a clean commit and unused valid branch names. | branch Feature; branch feature; branch HEAD; branch bad/name; branch 9bad; branch with 33 characters. | First succeeds; case collision gives E_EXISTS; remaining invalid names give E_ARGUMENT. No accidental ref directories or truncated names. |

**Staging, snapshots, and object identity**

| ID | Initial conditions | Commands or actions | Expected observable results |
| --- | --- | --- | --- |
| B01 | Unborn repo; f.txt contains "one\n". | add -- f.txt; edit to "two\n"; status; commit -m First --author Tester --timestamp 10. | Before commit status is index A/worktree M. Commit stores "one\n"; afterward index is unchanged relative to HEAD and working status is M. |
| B02 | Committed f.txt contains "one\n". | Edit to "two\n"; add -- f.txt; edit to "three\n"; diff --staged; diff; unstage -- f.txt. | Staged diff is one-to-two; working diff two-to-three. Unstage restores index to one without changing working three. |
| B03 | Unborn repo with files a, d/b, d/c. | add -- d d/b a a; repeat identical add. | First stages each path once; count 3. Repeated add reports 0. Index paths are strictly sorted, with no duplicates. |
| B04 | Committed directory d has d/a and d/b. | Remove d and its files using ordinary filesystem actions; add -- d; commit -m Delete --author Tester --timestamp 20. | Both deletions are staged despite missing directory; new root has no d entry because it contains no remaining files. Older d trees remain stored. Deleted files do not reappear during commit. |
| B05 | Tracked clean a and unrelated untracked b in the same directory. | rm -- a; then unstage -- a; restore --force -- a. | Removal stages absence and deletes only a; b is identical throughout. Unstage restores I but not W; forced restore recreates exact a bytes. |
| B06 | Tracked file a with local edited bytes. | rm -- a; rm --cached -- a; status; unstage -- a; rm --force -- a. | First fails E_DIRTY. Cached removal leaves bytes and reports index D/worktree A. Unstage preserves local bytes. Forced removal succeeds and stages deletion. |
| B07 | Snapshot contains f as a regular file; record its commit as C0. | Replace working f with directory f containing x; add -- f; commit -m Shape --author Tester --timestamp 21, recording C1; switch --detach C0; switch --detach C1. | add simultaneously stages f's deletion and f/x's addition. Each tree is valid, and clean switching performs both structural transitions safely. |
| B08 | Index contains f; working f has become directory containing x. | add -- f/x only. | E_STRUCTURE because unselected index file f remains; entire index unchanged. |
| B09 | Unborn repo; files a and b contain identical arbitrary binary bytes. | add -- a b; inspect index and object store; commit -m Duplicates --author Tester --timestamp 22; add -- a b. | Both entries reference one blob ID and one physical blob file. Initial commit creates exactly one tree and one commit. Repeated add creates no object. Renaming via delete/add reuses the blob. |
| B10 | Empty file empty and file alpha containing "alpha\n". | add -- empty alpha; cat-object with each vector's blob ID; cat-object --raw with each vector's blob ID. | Exact vector IDs below; sizes 0 and 6; raw empty output has zero bytes; alpha output has exactly six bytes. No framing LF is added to raw output. |
| B11 | Binary file bin.dat containing bytes 00 ff 80 0d 0a 1a and text.txt containing UTF-8 with CRLF. | add -- bin.dat text.txt; commit -m Bytes --author Tester --timestamp 23; modify both; restore --force -- bin.dat text.txt; switch to another clean revision and back to the captured commit. | Original bytes, including NUL, invalid UTF-8, CRLF, and 1a, round-trip exactly. No encoding failure or newline conversion. |
| B12 | Two separate repositories have identical path sets, bytes, author, message, timestamp, and parent histories. | Stage files in opposite orders and commit. | Tree/commit IDs and uncompressed object bytes match across repositories. Compressed bytes need not match across zlib versions. |
| B13 | Committed file a is edited to different bytes of the same length; its modification time is reset to the old value. | status; diff; add -- a; commit -m Same-size --author Tester --timestamp 24. | Change is detected and new blob identity is used. Stat similarity cannot hide it. |
| B14 | Clean committed repo; empty directory named empty-directory; no path named missing. | add -- empty-directory; add -- missing; add -- .; unstage -- .; restore -- . . | First two give E_PATH. "." operations may be no-ops; duplicates do not inflate counts. restore reports 0 when selected bytes already match I. |
| B15 | Index contains a file not present in HEAD. | unstage -- that-file. | Index entry disappears; working file becomes untracked. No working-byte deletion. |
| B16 | Committed file a is staged for deletion but remains on disk after rm --cached. | diff; diff --staged; add -- a. | Working diff is an addition from absence; staged diff is a deletion; add restores its index mapping and returns to clean if bytes still match HEAD. |
| B17 | Unborn repo with README.txt, src/a.txt, and src/nested/b.txt; all file contents distinct. | add -- .; inspect index; commit -m Hierarchy --author Tester --timestamp 25; inspect root and descendant trees with cat-object --raw. | Index has exactly three full paths. Commit refers to root tree with names README.txt and src. src tree has a.txt and nested; nested tree has b.txt. Exactly three tree objects and three blobs exist; no tree entry name contains "/". |
| B18 | Unborn repo with left/f.txt and right/f.txt containing identical bytes. | add -- .; commit -m Shared --author Tester --timestamp 26; inspect trees; remove both working files; restore --force -- .; fsck. | Two indexed file paths, one blob, and two physical trees: one root and one shared child tree. Root's left and right entries reference the same child ID. Both files restore independently. Sharing is valid and fsck reports no error. |
| B19 | Repository from B18. | Change only left/f.txt to new bytes; add -- left/f.txt; commit -m Left-only --author Tester --timestamp 27; inspect old/new roots and child IDs. | New left child and new root are created; right still references the original child. Exactly two additional trees and one additional blob exist. Old committed bytes remain recoverable; directory location is absent from child payloads. |
| B20 | Unborn repository containing only empty directories. | add -- .; commit -m Empty --author Tester --timestamp 28 --allow-empty; inspect root; fsck. | Index empty; one empty root tree and one commit, zero blobs. No objects or root entries represent the empty working directories. |

Known object vectors, with payloads specified exactly:

| Type | Payload bytes | Expected SHA-256 object ID |
| --- | --- | --- |
| blob | Zero bytes. | 473a0f4c3be8a93681a267e3b1e9a7dcda1185436fe141f7749120a303721813 |
| blob | Six bytes: 61 6c 70 68 61 0a. | 9f8bf964b2f278e643f6ee93dd5980698a5f515048b2a27134a294e5e3376180 |
| tree | UTF-8 of {"entries":[],"version":1}, exactly 26 bytes, without LF. | 20539f7e954abdca3f0240e1673385c698c8136030aa5ca192ce007bd9e8d789 |

**Unicode, paths, and platform boundaries**

| ID | Initial conditions | Commands or actions | Expected observable results |
| --- | --- | --- | --- |
| C01 | Files at café/नमस्ते.txt, 数据/😀.bin, and two words.txt, all NFC and host-representable. | add -- .; commit -m Unicode --author Tester --timestamp 30; remove working files; restore --force -- . | Original names and byte contents return; JSON stores literal Unicode, valid UTF-8, and deterministic path order. |
| C02 | Host can represent a decomposed filename consisting of "e" plus U+0301 and ".txt". | add that path; separately inject that spelling into an otherwise valid tree fixture. | Working input gives E_PATH without renaming it. Stored non-NFC fixture gives E_CORRUPT. |
| C03 | Case-sensitive host permits both A.txt/a.txt and Dir/x/dir/y fixtures. | add -- . for each isolated collision fixture; status. | add gives E_STRUCTURE for a resultant snapshot collision; no partial index. status gives E_PATH for the invalid working naming set. |
| C04 | Valid repository. | Select ../outside, /absolute, C:/outside, a path containing backslash, or .pygit/index.json. | E_PATH; no read/write outside repository and no tracked metadata. |
| C05 | Host permits a filename named CON.txt, one ending in dot/space, or a component with colon/control character. | add each isolated path. | E_PATH; no normalization or silent omission. Where the host cannot create the name, use a stored fixture and require E_CORRUPT. |
| C06 | Working symlink to an external file, directory symlink, FIFO/special file, or host reparse point in the selected scope. | add -- .; separately attempt a restore through the link. | E_PATH; external target bytes unchanged; no hanging read on FIFO. Host-unsupported creation cases are explicitly skipped. |
| C07 | Clean tracked file and an outside hard-link alias, where supported. | Restore the tracked name to a different committed version, then rm it in a separate clean case. | Outside alias's bytes remain unchanged by restoration; removing the selected name does not remove/change the alias. PyGit need not preserve the link relationship. |
| C08 | Nested .pygit entry inside an otherwise untracked directory. | add that directory; status; separately cat-object for a known valid blob. | Recursive scans give E_NESTED; object inspection succeeds because it does not scan unrelated working entries. |
| C09 | Valid snapshot at a representable maximum-length component/path boundary; an otherwise equivalent name exceeds a contract limit. | Stage the valid fixture; stage the too-long fixture or inspect it as stored data. | In-limit data works if the host represents it; working invalid path gives E_PATH, stored invalid path gives E_CORRUPT. No truncation. |

**History, references, and differences**

| ID | Initial conditions | Commands or actions | Expected observable results |
| --- | --- | --- | --- |
| D01 | Linear C0 → C1 → C2, with child timestamps smaller than parent timestamps. | log; log --max-count 2; log C1. | Orders are C2,C1,C0; C2,C1; and C1,C0. Generation, not timestamp, determines order. |
| D02 | main and feature share C0 and diverge to O and T. | branch; log --all; delete feature while HEAD is main at O. | Branch names sorted; shared C0 appears once; equal-generation tips sorted by full ID; deletion refused E_STATE because T is not ancestral to O. |
| D03 | main contains a merge whose second parent is feature's tip. | branch -d feature; log --all. | Deletion succeeds through second-parent ancestry. Objects and main history remain intact. |
| D04 | Clean born repo. | switch --detach HEAD; edit/add/commit; branch saved HEAD; switch saved. | Detached commit advances only HEAD, original branch ref unchanged; saved points to new commit; switch attaches to saved and preserves its snapshot. |
| D05 | Valid blob and tree IDs plus a valid commit ID. | log with blob/tree ID; cat-object with truncated/uppercase ID; log nonexistent valid-length ID. | Non-commit and unknown revisions give E_REVISION; invalid cat-object ID spelling gives E_ARGUMENT; no prefix resolution. |
| D06 | File changes from "A\nB\n" to "B\nA\n". | diff. | Exact operations: delete "A\n", equal "B\n", insert "A\n". Edit cost is two; alternative minimum beginning with insert is not selected. |
| D07 | File changes from "a\n" to "a", and another from empty to "x\n". | diff for each; also compare missing versus present empty file. | Newline change is delete "a\n", insert "a". Empty-to-line is one insert. Missing-to-empty emits A with edits [], distinct from no change. |
| D08 | File changes from "a\r\n" to "a\n"; another contains valid UTF-8 plus NUL; another contains invalid UTF-8. | diff. | CRLF difference is visible in text line records. NUL/invalid UTF-8 records have kind binary and edits null, with correct old/new IDs. |
| D09 | An unchanged 2,000-line file is edited within thresholds; isolated 2,001-line and 1 MiB-plus-one-byte files are changed. | diff. | First uses minimum-cost text edits. Either exceeded text threshold selects binary summary; no E_LIMIT merely for exceeding a diff-text threshold. |
| D10 | Only unrelated untracked files differ; committed/indexed files are clean. | diff; diff --staged; diff HEAD HEAD; diff -- . | All streams empty. Explicit unmatched non-dot path filter gives E_PATH. |
| D11 | Multiple changed paths and one directory filter. | diff REV1 REV2 -- directory; run reverse diff REV2 REV1. | Only matching paths appear, sorted; reverse comparison reverses old/new and A/D semantics, with its own specified text tie-breaking. No objects are written. |

**Restoration and ordinary-failure safety**

The failure cases below must be reproducible on the chosen supported platform without third-party packages, administrator privileges, a special filesystem, disk exhaustion, or timing-dependent permission changes. Real permission-denial tests may supplement them; they are not the only permitted mechanism.

A test harness may use standard-library test doubles at filesystem/stream boundaries to introduce one controlled OSError. It may install those boundary doubles before launching the CLI's normal module entry point in an isolated child process. The invocation arguments, stdout/stderr, exit code, repository bytes, and working bytes remain the observable test interface. No production-only test flags, extra commands, private PyGit function calls, module-name assumptions, or substitutions for hashing, serialization, merge, history, or transaction logic are allowed.

Each injected error occurs once at a documented filesystem event and leaves subsequent I/O healthy, including rollback I/O. The harness must establish that the event actually occurred and the fault was triggered; a run that misses the event is an invalid test setup, not a pass. Failure targeting is based on affected repository paths and observable state, not a hard-coded overall syscall count or a prescribed temporary filename. Wrapping the public filesystem/stream boundary actually used by an implementation is permitted. Each selected fault must surface as E_IO; silently retrying it and reporting success does not satisfy these acceptance cases.

"Publication" in this table means any filesystem operation that makes the named final file's content or presence change. This definition does not prescribe a write, rename, replacement, or transaction technique. For faults declared before an operation takes effect, the injected operation makes no filesystem change.

| Fault | Initial conditions and exact injection event | CLI action | Required observation |
| --- | --- | --- | --- |
| IO1 | Clean committed a and b; both now contain different working bytes. Fail one attempted read of selected working file b, before that read returns bytes. | add -- a b | E_IO; neither staged mapping changes. Existing W bytes remain intact. |
| IO2 | Clean committed a; working a is modified. Fail the first publication attempt that would change .pygit/index.json, before it takes effect. | add -- a | E_IO; original index/refs/HEAD/W remain exact. A new valid unreachable blob is allowed. |
| IO3 | Current and target snapshots each contain different bytes at two existing regular files in separate top-level directories; unrelated untracked sentinel.txt exists. Once at least one selected path has changed and at least one selected path still differs from its target, fail the next operation that would mutate a selected working path, before it takes effect. | switch target; in a separate fresh fixture, restore --source target --force -- . | E_IO; every original tracked byte/presence and logical metadata value returns, and sentinel.txt remains identical. The harness records the intermediate changed state and the triggered fault. |
| IO4 | Born attached HEAD; one valid staged change. Fail publication of the current branch file, before it takes effect. | commit -m Fault --author Tester --timestamp 50 | E_IO; old branch/HEAD/index/W remain exact. Valid new tree/commit objects may remain unreachable. Repeat with detached HEAD and fail publication of HEAD itself. |
| IO5 | A valid pending merge with every conflict resolved and no unstaged changes. Fail removal of MERGE.json, before it takes effect. | merge --continue | E_IO; restore the original pending merge state, index, branch, and working bytes, regardless of which other metadata publications had already occurred. New valid unreachable objects are allowed. |

Every fault case also checks that the process exits normally with the specified error contract, its own LOCK is gone, tmp is empty, and a subsequent fsck without injected faults succeeds with no errors. Unreachable objects are permitted exactly as above. Process kills and permanently failing rollback I/O are outside these cases.

| ID | Initial conditions | Commands or actions | Expected observable results |
| --- | --- | --- | --- |
| E01 | Clean main and another branch with different contents. | Edit a tracked file; switch other. Then stage that edit and retry. | Both attempts give E_DIRTY, covering unstaged and staged dirt; no files/index/refs change. |
| E02 | Target branch introduces u; current branch does not track u; working u exists, including the case of identical target bytes. | switch target; restore --source target --force -- u. | Both give E_COLLISION; u remains byte-identical. Force does not authorize untracked overwrite. |
| E03 | Target needs directory p/x; working untracked regular file p exists. In a separate fixture target needs file q; working q contains untracked q/z. | switch target for each fixture. | E_COLLISION for ancestor and descendant obstructions; all unrelated and tracked paths are unchanged. |
| E04 | Tracked file a has modified bytes; file b is locally deleted. | restore -- a b; restore --force -- a b. | First gives E_DIRTY and preserves both states. Forced restore restores both exact index values; index and HEAD are unchanged. |
| E05 | Current commit lacks old.txt; historical commit has it; destination is absent. | restore --source HISTORICAL -- old.txt. | File appears with historical bytes, index/HEAD unchanged, status shows untracked. Repeating the restore now refuses E_COLLISION because it is working-only. |
| E06 | Current H/I contain a; selected historical source lacks a; a is clean. | restore --source HISTORICAL -- a; status. | Working a disappears; index and HEAD still contain it; status shows unstaged D. Commit without staging still refuses E_EMPTY. |
| E07 | Multi-file restore target contains a needed corrupt blob; at least one earlier-sorted target file differs. | restore --source TARGET --force -- . | E_CORRUPT before any working change; no partly restored early file. |
| E08 | IO1 and IO2 fixtures from the controlled-failure table, tested separately. | Run their add commands with the specified single fault. | E_IO; complete original logical state and W preserved; any extra blob is valid/unreachable; no leaked lock/tmp. Real permission-denial variants may be added when the host supports them. |
| E09 | IO3 fixture from the controlled-failure table. | Exercise both switch and restore with the specified intermediate-state fault in separate fixtures. | E_IO; original working bytes/presence and logical metadata restored after an observed partial operation; no misleading success output or leftover lock/tmp. |
| E10 | LOCK exists with arbitrary bytes and its contents are recorded. | status; fsck; add -- . | All give E_LOCKED, exit 5; lock bytes and all other bytes unchanged. Help/version still succeed. |
| E11 | Two processes attempt repository commands while one still owns the lock. | Start a second command during the first's ownership. | Second fails E_LOCKED; at most one operation mutates state. On normal first completion, lock disappears and fsck succeeds. |
| E12 | Clean repo with a 64 MiB file and a separate 64 MiB-plus-one-byte file. | add the in-limit file; then attempt add of the oversized file. | First succeeds; second gives E_LIMIT, retaining the prior index and without a truncated object. |
| E13 | Valid generated fixtures at 10,000 paths, 10,000 reachable commits, and 1,000 branches, tested independently. | Inspect/history at the limits; attempt a mutation exceeding each relevant limit by one. | In-limit operations complete correctly; exceeding mutation gives E_LIMIT. No recursion-depth crash or silent history truncation. A malformed stored fixture over a limit is E_CORRUPT. |
| E14 | IO4 fixtures for attached and detached HEAD, tested separately. | Run the specified commit with its publication fault. | E_IO; no branch or detached HEAD advances; staged change remains available. Any newly stored tree/commit is valid and fsck lists it as unreachable. |
| E15 | IO5 fixture with a resolved pending merge. | merge --continue with its cleanup fault; then inspect state without fault injection. | E_IO; merge remains pending exactly as before the command, including original parent tips and saved metadata. A later fault-free continuation succeeds. |

**Merges and conflict lifecycle**

| ID | Initial conditions | Commands or actions | Expected observable results |
| --- | --- | --- | --- |
| F01 | O already contains T in its ancestry. | merge T with valid metadata. | already-up-to-date, no new objects, no ref/index/worktree changes, no pending state. |
| F02 | O is a strict ancestor of T; tracked state clean; untracked unrelated note exists. | merge T with valid metadata. | fast-forward to T without new commit; note preserved; current branch name unchanged. |
| F03 | Unique base B; O modifies a only; T modifies b only. | merge T with valid metadata from O. | Clean merge commit with [O,T], both edits, saved author/message/time, no pending state, and clean tracked state. |
| F04 | Unique base; both tips independently add same path with identical bytes, or both make same modification, or both delete the same path. | Merge each isolated fixture. | No conflict; shared value/absence appears in result. A divergent merge still creates two-parent commit even if the result tree equals O. |
| F05 | Same path has unequal changes on both tips, including disjoint line changes. | merge T with metadata. | Exit 6; one conflict; HEAD/ref remain O; stage-zero/W retain O; raw index contains exact B/O/T values; no conflict markers or sidecars. |
| F06 | Base lacks x; both tips add different x bytes. Separately, one tip deletes a base file while other modifies it. | merge each fixture. | Add/add and modify/delete conflicts. null accurately records absence. When O deleted the file, working path remains absent. |
| F07 | Active conflict; working conflict file edited to a chosen result. | merge --continue before add; then add -- path; merge --continue. | First E_UNRESOLVED. Add removes conflict record and stages chosen bytes. Continue creates [O,T] with original saved metadata and exact chosen bytes. |
| F08 | Active conflict at file x selected for deletion, including a conflict whose ours value is already absent. | Remove working x manually if present; add -- x; merge --continue. In another fixture use rm --cached -- x and inspect remaining W. | Missing conflicted path is a valid add match, resolving to absence even with N=0 and R=1. Cached removal leaves W; continue refuses E_DIRTY while a managed deleted path still has a file. |
| F09 | Active conflict has been resolved/staged; file edited again without staging. | merge --continue. | E_DIRTY; pending state and refs unchanged. Re-add then continue commits latest staged bytes. |
| F10 | Pending merge has non-conflicting additions and resolved conflicts; user also creates and stages unrelated extra.txt. | merge --abort. | Original managed bytes and original index return exactly to O; merge-introduced files disappear; edits at managed paths are discarded; extra.txt survives unchanged as untracked; pending state disappears. |
| F11 | Pending merge with conflicts; branches old and another exist and new does not. | commit -m Blocked --author Tester --timestamp 40; unstage -- .; branch new; branch -d old; switch another; merge another -m Blocked --author Tester --timestamp 40. Separately branch with no args and log. | Forbidden mutations give E_STATE; listing/history remain available. diff without two REVs refuses while conflicts remain; diff O T works. |
| F12 | Divergent tips with two best common ancestors: base R; A and B each parent R; M1 parents [A,B]; M2 parents [B,A]; tips are M1/M2 with distinct IDs. | Merge M2 from attached M1. | E_BASE; no guessed ancestor or mutation. This graph is a data fixture, not a required CLI construction sequence. |
| F13 | Two independent root histories stored in one otherwise valid repository and referenced by branches. | Merge one into the other. | E_UNRELATED; no implicit empty merge base. |
| F14 | Divergent histories' base/ours/theirs union contains p and p/x, or distinct casefold-colliding directory spellings. | Merge with valid metadata. | E_STRUCTURE before any conflict/index/worktree change, even if a possible result alone would be valid. |
| F15 | Before divergence merge, untracked file occupies a path present only in base/theirs and absent in O. | Merge. | E_COLLISION, preserving untracked bytes and leaving no pending state. |
| F16 | Pending merge; replace a managed file with directory containing a newly created outside/untracked descendant. | merge --abort. | E_COLLISION; abort does not recursively delete the new descendant, and pending state remains unchanged. |
| F17 | All conflicts resolved to the original O content, with no unstaged changes. | merge --continue. | Two-parent merge commit is still created; no E_EMPTY. The tree may reuse O's tree. |

**Corruption and format conformance**

For corrupt object payload fixtures, any digest/name recomputation needed to isolate a schema fault is part of fixture preparation, not a relaxation of the format. A fixture with multiple faults can produce any applicable E_CORRUPT diagnosis. Run fsck on each isolated malformed fixture and require a report with errors and exit 3. An ordinary command must reject a fault within its declared validation scope. Reachability alone does not put historical snapshot contents in every ordinary command's scope.

| ID | Initial conditions | Commands or actions | Expected observable results |
| --- | --- | --- | --- |
| G01 | Missing, unsupported, CRLF-terminated, or extra-byte FORMAT; malformed HEAD; empty current branch file; symbolic HEAD pointing to a missing non-main ref. | fsck and status in separate fixtures. | E_CORRUPT/report errors; no auto-init, upgrade, or repair. |
| G02 | Invalid/truncated zlib stream; wrong wrapper; valid stream with trailing bytes; two concatenated streams; preset-dictionary stream. | cat-object and fsck for each fixture. | Corruption detected, no partial raw stdout, bounded reads/decompression. |
| G03 | Decompressed envelope has wrong type, extra header space, negative/leading-zero length, missing NUL, mismatched payload length, or trailing uncompressed bytes. | cat-object and fsck. | Each rejected as corrupt even when zlib itself is valid. |
| G04 | Valid object moved to a different valid-looking ID path, or bytes edited without corresponding ID. | fsck; ordinary operation if referenced. | Digest mismatch detected; existing object is not overwritten to hide the error. |
| G05 | Canonical tree/commit/index fixture altered to duplicate a key, use an unknown field, change integer version to true, add BOM/whitespace, reorder keys, escape literal non-ASCII, add/remove framing LF, or encode a surrogate. | fsck for each isolated fixture. | Exact representation/schema violation reported. Payloads must have no LF; metadata must have exactly one. |
| G06 | A directory tree has duplicate names, unsorted entries, a file and directory with the same name, portable aliases, a name containing "/", or an entry whose target type differs from its type field. | fsck; switch/restore to a commit containing it. | E_CORRUPT; unsafe target never appears on disk. Flat index file-prefix collisions remain separate index-schema errors. |
| G07 | Commit references missing/wrong-type tree or parent, repeats a parent, has more than two parents, or has invalid author/message/time. | fsck for every fixture; log for parent/history or local commit faults; restore --source COMMIT --force -- . for tree-reference faults. | Commands whose required scope includes the fault report E_CORRUPT. A locally valid commit with only a broken tree reference can still appear in log. |
| G08 | Referenced blob removed from disk, including a conflict-only blob or index-only blob. | fsck; status and add/restore whose declared scopes include that blob. | Missing reference detected, even when the working file still happens to have identical bytes. No silent repair from W. |
| G09 | Valid unreachable blob/tree/commit fixture, with valid closure. | fsck; cat-object on its IDs; log its commit ID. | Exit 0; every unreachable ID listed; raw inspection/full-ID history works; no garbage collection. |
| G10 | An unreachable object is locally malformed while its filename/layout, common metadata, and current snapshot/index are valid. | status; then fsck. | status succeeds because the malformed payload is outside its scope; fsck reports corruption. |
| G11 | Nonempty conflicts without MERGE.json; pending merge with wrong ours/branch, invalid managed set, or conflict values contradicting its snapshots. Separately, a locally/snapshot-consistent pending merge falsely claims a unique best base. | fsck for every fixture; status for the common/snapshot-invariant faults; merge --continue for the false-base fixture after all conflicts are resolved. | Each command checking the relevant invariant reports E_CORRUPT. Zero current conflicts with a valid pending merge is accepted. Read-only commands need not re-prove ancestry claims. |
| G12 | A common metadata path is a symlink/reparse point, an unexpected file appears immediately under .pygit, or idle tmp is nonempty. Separately, an unrelated object-store path has an invalid name or is a symlink. | fsck for every fixture; status for common-metadata faults; cat-object targeting the bad object path when its ID is syntactically valid. | In-scope corruption is rejected and links are never followed. status succeeds for solely unrelated object-store faults. Existing LOCK is instead E_LOCKED. |
| G13 | Tiny compressed file expands beyond permitted envelope/payload size; oversized physical object; oversized index/MERGE file. | fsck or cat-object as applicable. | E_CORRUPT without accepting/truncating data; processing must remain bounded by the stated format limits rather than claimed lengths. |
| G14 | A reachable object at an existing blob ID has been corrupted, while W still contains the original content. | add that file. | E_CORRUPT; existing physical object is not replaced with newly hashed working bytes. |
| G15 | Valid repository with pending merge or ordinary index. | Read-only status, branch, log, diff, cat-object, and fsck as permitted; compare all repository bytes afterward. | No persistent byte changes, object creation, metadata reformatting, leftover lock, or temp files. |
| G16 | C0 stores old bytes for a; child C1 stores distinct new bytes and is current HEAD. Remove C0's old blob, which C1/index do not reference. All commit records remain valid. | status; log; restore --source C0 --force -- a; fsck. | status is clean and log includes both commits. Restore refuses E_CORRUPT without changing a. fsck reports the missing historical blob. |
| G17 | Locally valid parent tree references a missing child tree, an empty child tree, or a blob under a tree-type entry. Fixture's commit payload remains locally valid. | cat-object --raw on the parent tree; fsck; restore from the affected commit. | Raw local inspection succeeds; fsck and restore reject the broken tree relationship. No child directory/file is partially restored. |
| G18 | Locally valid root references the same valid 501-file child tree at 20 different directory names, yielding 10,020 logical files. Separately, a valid-name chain yields a file with 129 path components or more than 4096 path bytes. | cat-object on the root; fsck; switch to the fixture's commit from a clean valid branch. | Root local inspection succeeds. Expanded snapshot checks give E_CORRUPT despite each immediate tree and each object's size being within limits. No physical-object deduplication reduces the logical file count. |
| G19 | main is current and valid; a non-current branch points to a commit with a malformed payload at a correctly named object path. Current index/HEAD and every raw ref file are valid. | status; log HEAD; branch; log --all; fsck. | status and log HEAD succeed. Branch listing, log --all, and fsck detect the malformed tip because their scopes include it. |

The format's acyclic-graph invariants are mandatory for both commits and directory trees. Ordinary SHA-256-valid cyclic fixtures are not realistically constructible because IDs include referenced IDs; malformed cycles with stale IDs must still be rejected as corruption. Tests must not assume that a digest-valid cryptographic fixed-point fixture can be manufactured. Shared acyclic subtrees, as in B18, must remain valid.

**Complete end-to-end acceptance scenario**

Use a new existing directory. No unrelated files are present initially. Create the following exact files with an editor or binary-file tool:

| Path | Exact contents |
| --- | --- |
| README.txt | UTF-8 "start\n". |
| data/payload.bin | Four bytes: 00 ff 10 0a. |
| notes/नमस्ते.txt | UTF-8 "नमस्ते\n", with an LF after the word. |

In this table every listed CLI command uses the full invocation. Capture commit IDs from stdout as C1, C2, C3, and C4. Replace symbolic revisions with captured full IDs when needed.

| Step | Command or external action | Required observation |
| --- | --- | --- |
| 1 | python -m pygit init | Unborn main; original files unchanged. |
| 2 | python -m pygit status | Three untracked file entries, sorted by UTF-8 stored path. |
| 3 | python -m pygit add -- . | {"resolved":0,"staged":3}; exact three blobs and no tree/commit yet. |
| 4 | python -m pygit commit -m "Initial snapshot" --author "Ujjwal" --timestamp 1700000100 | Record C1; root parents []; expanded snapshot contains all three files. There are three trees: root, data, and notes. fsck would count three blobs, three trees, one commit. |
| 5 | python -m pygit branch feature | feature and main both at C1; HEAD stays main. |
| 6 | python -m pygit switch feature | Attached to feature, clean. |
| 7 | Change README.txt to "feature\n"; create feature.txt with "new\n". | Only working state changes. |
| 8 | python -m pygit add -- README.txt feature.txt | Two staged mappings change. |
| 9 | python -m pygit commit -m "Feature changes" --author "Ujjwal" --timestamp 1700000101 | Record C2 with parent C1 and four files; feature advances only. New root tree; data and notes child trees reuse their C1 IDs. |
| 10 | python -m pygit switch main | README becomes "start\n"; feature.txt disappears; binary/Unicode files remain exact. |
| 11 | Change README.txt to "main\n". | One unstaged modification. |
| 12 | python -m pygit add -- README.txt | One staged change. |
| 13 | python -m pygit commit -m "Main changes" --author "Ujjwal" --timestamp 1700000102 | Record C3, parent C1; main advances; feature still C2. |
| 14 | Create private.txt with "keep me\n". | An unrelated untracked file exists. |
| 15 | python -m pygit merge feature -m "Merge feature" --author "Ujjwal" --timestamp 1700000103 | Exit 6; conflicts exactly ["README.txt"]; HEAD/main remain C3. README remains "main\n"; nonconflicting feature.txt appears as "new\n"; private.txt preserved. MERGE base=C1, ours=C3, theirs=C2. |
| 16 | python -m pygit status | README is U/U; feature.txt is staged A; private.txt is ?/?; merge field is non-null. |
| 17 | python -m pygit merge --continue | E_UNRESOLVED; no state change. |
| 18 | Change README.txt to "main + feature\n". | Conflict remains unresolved until staged. |
| 19 | python -m pygit add -- README.txt | {"resolved":1,"staged":1}; conflict list becomes empty. |
| 20 | python -m pygit merge --continue | Record C4; parents exactly [C3,C2], expanded snapshot has four tracked files, metadata retained from step 15. New root tree; data and notes still reuse their C1 IDs. Pending state disappears; private.txt stays untracked. |
| 21 | python -m pygit log | C4 first; then C2/C3 sorted by full ID because both generation 1; C1 last; each exactly once. |
| 22 | python -m pygit branch -d feature | Allowed because C2 is the second parent of C4. Its objects remain. |
| 23 | Replace data/payload.bin with different bytes and delete notes/नमस्ते.txt. | Two unstaged changes; private.txt still untracked. |
| 24 | python -m pygit restore -- data/payload.bin notes/नमस्ते.txt | E_DIRTY; neither modification nor deletion is silently discarded. |
| 25 | python -m pygit restore --force -- data/payload.bin notes/नमस्ते.txt | {"restored":2}; binary and Unicode files exactly restored from I; HEAD/index unchanged. |
| 26 | python -m pygit switch --detach C1 | Detached at C1; README="start\n"; feature.txt absent; private.txt preserved. |
| 27 | python -m pygit status | branch null, head C1, only private.txt untracked, merge null. |
| 28 | python -m pygit switch main | Attached at C4; README="main + feature\n"; feature.txt="new\n"; all other tracked bytes exact. |
| 29 | python -m pygit diff C1 C4 | Exactly README.txt modified and feature.txt added, sorted by UTF-8 path; binary and Unicode paths omitted because unchanged. |
| 30 | python -m pygit cat-object --raw C4 | Exact canonical commit payload without added LF; inspect tree field, [C3,C2], saved timestamp, author, and message. |
| 31 | python -m pygit fsck | Exit 0, no errors, no unreachable objects; exactly seven blobs, six trees, and four commits. The trees are four distinct roots plus the two shared directory trees for data and notes. All committed snapshots and all staged-resolution blobs remain reachable. |
| 32 | python -m pygit status | Attached main at C4; merge null; only private.txt appears untracked. Its exact bytes are still "keep me\n". |

The final repository contains one branch, main at C4; four reachable commits; seven unique file-content blobs; six unique trees (four roots and two reused directory trees); no merge state; no idle lock or temp files; and the preserved untracked private.txt. No action in this scenario stores private.txt as an object.

# 7. Official Documentation References

**Python language, object model, and built-in behavior**

- [Python 3.13 Language Reference: Data model](https://docs.python.org/3.13/reference/datamodel.html)
- [Python 3.13 Language Reference: Expressions](https://docs.python.org/3.13/reference/expressions.html)
- [Python 3.13 Language Reference: Compound statements](https://docs.python.org/3.13/reference/compound_stmts.html)
- [Python 3.13 Language Reference: The import system](https://docs.python.org/3.13/reference/import.html)
- [Built-in types](https://docs.python.org/3.13/library/stdtypes.html)
- [Built-in functions](https://docs.python.org/3.13/library/functions.html)
- [Built-in exceptions](https://docs.python.org/3.13/library/exceptions.html)

**Data modeling, collections, iteration, and interfaces**

- [collections — Container datatypes](https://docs.python.org/3.13/library/collections.html)
- [dataclasses — Data classes](https://docs.python.org/3.13/library/dataclasses.html)
- [enum — Enumerations](https://docs.python.org/3.13/library/enum.html)
- [itertools — Iterator tools](https://docs.python.org/3.13/library/itertools.html)
- [typing — Type hints](https://docs.python.org/3.13/library/typing.html)
- [contextlib — Context-manager utilities](https://docs.python.org/3.13/library/contextlib.html)

**CLI and filesystem interfaces**

- [argparse — Command-line arguments and subcommands](https://docs.python.org/3.13/library/argparse.html)
- [pathlib — Filesystem paths](https://docs.python.org/3.13/library/pathlib.html)
- [os — Operating-system interfaces](https://docs.python.org/3.13/library/os.html)
- [io — Text and binary streams](https://docs.python.org/3.13/library/io.html)
- [tempfile — Temporary files and directories](https://docs.python.org/3.13/library/tempfile.html)

**Encoding, object identities, compression, and time**

- [json — JSON encoding and decoding](https://docs.python.org/3.13/library/json.html)
- [hashlib — Hash functions and message digests](https://docs.python.org/3.13/library/hashlib.html)
- [zlib — Compression and decompression](https://docs.python.org/3.13/library/zlib.html)
- [unicodedata — Unicode properties and normalization](https://docs.python.org/3.13/library/unicodedata.html)
- [datetime — Date and time types](https://docs.python.org/3.13/library/datetime.html)
- [time — Time access and conversions](https://docs.python.org/3.13/library/time.html)

**Testing, process execution, and environment isolation**

- [unittest — Testing framework](https://docs.python.org/3.13/library/unittest.html)
- [unittest.mock — Test doubles and controlled behaviors](https://docs.python.org/3.13/library/unittest.mock.html)
- [subprocess — Child-process management](https://docs.python.org/3.13/library/subprocess.html)
- [venv — Virtual environments](https://docs.python.org/3.13/library/venv.html)

**Official Git concepts and command semantics**

- [Git data model — Objects, references, index, and reflogs](https://git-scm.com/docs/gitdatamodel)
- [Git glossary — Version-control terminology](https://git-scm.com/docs/gitglossary)
- [git-add — Staging file contents](https://git-scm.com/docs/git-add)
- [git-diff — Comparing working, staged, and committed content](https://git-scm.com/docs/git-diff)
- [git-switch — Branch and detached-HEAD semantics](https://git-scm.com/docs/git-switch)
- [git-restore — Restoring tracked content](https://git-scm.com/docs/git-restore)
- [git-merge — Ancestry, fast-forwards, and conflicts](https://git-scm.com/docs/git-merge)
- [git-fsck — Object and reference integrity](https://git-scm.com/docs/git-fsck)


