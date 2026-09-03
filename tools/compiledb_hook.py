# Post-build hook: regenerate compile_commands.json after every build so
# clangd always has entries for newly added source files.
Import("env")
import platform
import subprocess

def generate_compilation_db(source, target, env):
    pio = "pio.exe" if platform.system() == "Windows" else "pio"
    subprocess.call([pio, "run", "-e", env["PIOENV"], "-t", "compiledb"],
                    cwd=env["PROJECT_DIR"])

env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", generate_compilation_db)
