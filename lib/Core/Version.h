#ifndef FW_VERSION_H
#define FW_VERSION_H

// FW_VERSION comes from git at build time (tools/version.py writes the
// git-ignored BuildVersion.h); "dev" only if that step did not run.
#if __has_include("BuildVersion.h")
#include "BuildVersion.h"
#endif

#ifndef FW_VERSION
#define FW_VERSION "dev"
#endif

#endif
