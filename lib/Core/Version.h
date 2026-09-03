#ifndef FW_VERSION_H
#define FW_VERSION_H

// The release workflow overwrites this with the git tag name before building
// release binaries. "dev" identifies locally built firmware and never matches
// a release tag, so local builds never self-update.
#define FW_VERSION "dev"

#endif
