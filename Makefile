# Crash Course 2, revived.
#
#   make            build xexmerge — the one thing here that needs compiling
#   make doritos    build it, then patch what is in game-data/ into output/
#   make check      would a kernel load the built default.xex, and are all 144
#                   patch writes in it
#   make clean      remove xexmerge and the compiler's objects
#
# `make` needs a C and a C++ compiler: gcc and g++, or clang. On Windows that means
# an MSYS2 / MinGW-w64 shell, which has all three:
#
#   pacman -S mingw-w64-ucrt-x86_64-toolchain make
#
# CROSS=x86_64-w64-mingw32- builds the Windows binary on Linux, linked static so the
# .exe needs no runtime DLLs beside it, and EXE=.exe names it that way:
#
#   make CROSS=x86_64-w64-mingw32-

MAKEFLAGS += --no-print-directory
PY    ?= python3
ARGS  ?=
EXE   ?= $(if $(CROSS),.exe,)

XEX_SRC = tools/xexmerge_src
XEX     = $(CURDIR)/xexmerge$(EXE)

.PHONY: all build doritos check clean
all: build

build:
	$(MAKE) -C $(XEX_SRC) CROSS="$(CROSS)" EXE="$(EXE)" OUT="$(XEX)"

doritos: build
	$(PY) revive.py $(ARGS)

check: build
	$(PY) check_hashes.py "output/Doritos Crash Course 2/default.xex"
	$(PY) verify_build.py "output/Doritos Crash Course 2/default.xex"

clean:
	$(MAKE) -C $(XEX_SRC) clean
	rm -f xexmerge xexmerge.exe
	rm -rf __pycache__ tools/__pycache__
