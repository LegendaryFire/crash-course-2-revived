# Xbox 360 XEX2 unpacker + .xexp merger (follows xenia's xex_module.cc / lzx.cc).
#
#   make                                  -> ../xexmerge
#   make CROSS=x86_64-w64-mingw32-        -> ../xexmerge.exe, and static, so the .exe
#                                            needs no compiler DLLs beside it
#   make CC=clang CXX=clang++             -> any toolchain; both are honoured
#   make clean
#
# On Windows, build this in an MSYS2 / MinGW-w64 shell:
#   pacman -S mingw-w64-ucrt-x86_64-toolchain make
# which gives plain `make`, so no CROSS is needed.

CROSS ?=
CC    ?= $(CROSS)gcc
CXX   ?= $(CROSS)g++
EXE   ?= $(if $(CROSS),.exe,)
OUT   ?= ../xexmerge$(EXE)
LDFLAGS += $(if $(CROSS),-static,)

CFLAGS   = -O2 -Imspack -DHAVE_CONFIG_H
CXXFLAGS = -O2 -Imspack -I.

OBJECTS = xexmerge.o lzxd.o system.o rijndael.o logstub.o

$(OUT): $(OBJECTS)
	$(CXX) -o $@ $(OBJECTS) $(LDFLAGS)

xexmerge.o: xexmerge.cc TinySHA1.hpp mspack/mspack.h mspack/lzx.h
	$(CXX) $(CXXFLAGS) -c $< -o $@
lzxd.o: mspack/lzxd.c mspack/lzx.h mspack/mspack.h mspack/readbits.h mspack/readhuff.h
	$(CC) $(CFLAGS) -c $< -o $@
system.o: mspack/system.c mspack/system.h mspack/mspack.h
	$(CC) $(CFLAGS) -c $< -o $@
rijndael.o: mspack/rijndael-alg-fst.c mspack/rijndael-alg-fst.h
	$(CC) -O2 -c $< -o $@
logstub.o: logstub.cc
	$(CXX) -O2 -c $< -o $@

clean:
	rm -f $(OBJECTS) $(OUT)

.PHONY: clean
