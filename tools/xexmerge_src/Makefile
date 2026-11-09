# Xbox 360 XEX2 unpacker + .xexp merger (follows xenia's xex_module.cc / lzx.cc).
#   make            -> ../xexmerge
#   ../xexmerge base.xex patch.xexp out_image.bin [out_header.bin]
CFLAGS = -O2 -Imspack -DHAVE_CONFIG_H
CXXFLAGS = -O2 -Imspack -I.

xexmerge: xexmerge.o lzxd.o system.o rijndael.o logstub.o
	g++ -o $@ $^
	mv $@ ../

xexmerge.o: xexmerge.cc TinySHA1.hpp
	g++ $(CXXFLAGS) -c $< -o $@
lzxd.o: mspack/lzxd.c
	gcc $(CFLAGS) -c $< -o $@
system.o: mspack/system.c
	gcc $(CFLAGS) -c $< -o $@
rijndael.o: mspack/rijndael-alg-fst.c
	gcc -O2 -c $< -o $@
logstub.o: logstub.cc
	g++ -O2 -c $< -o $@
clean:
	rm -f *.o
