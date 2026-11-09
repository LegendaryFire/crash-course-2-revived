// Standalone Xbox 360 XEX2 unpacker + .xexp (title update) merger.
// The algorithm follows xenia's src/xenia/cpu/xex_module.cc (ReadImage + ApplyPatch)
// and lzx.cc, with the struct layouts from kernel/util/xex2_info.h.
//   xexmerge <base.xex> <patch.xexp> <out_image.bin> [out_header.bin]
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <algorithm>

extern "C" {
#include "rijndael-alg-fst.h"
#include "mspack.h"
#include <lzx.h>
}
#include "TinySHA1.hpp"

static const uint8_t xe_xex2_retail_key[16] = {
    0x20, 0xB1, 0x85, 0xA5, 0x9D, 0x28, 0xFD, 0xC3,
    0x40, 0x58, 0x3F, 0xBB, 0x08, 0x96, 0xBF, 0x91};

// optional header keys
static const uint32_t OPT_FILE_FORMAT_INFO = 0x000003FF;
static const uint32_t OPT_EXECUTION_INFO = 0x00040006;
static const uint32_t OPT_DELTA_PATCH_DESCRIPTOR = 0x000005FF;
static const uint32_t OPT_BASE_ADDRESS = 0x00010201;

// xex2_opt_delta_patch_descriptor, whose version fields are 32-bit values
enum {
  DESC_TARGET_VERSION = 0x04, DESC_SOURCE_VERSION = 0x08, DESC_DIGEST_SOURCE = 0x0C,
  DESC_IMAGE_KEY_SOURCE = 0x20, DESC_TARGET_HEADERS = 0x30,
  DESC_HEADERS_SOURCE_OFFSET = 0x34, DESC_HEADERS_SOURCE_SIZE = 0x38,
  DESC_HEADERS_TARGET_OFFSET = 0x3C, DESC_IMAGE_SOURCE_OFFSET = 0x40,
  DESC_IMAGE_SOURCE_SIZE = 0x44, DESC_IMAGE_TARGET_OFFSET = 0x48, DESC_INFO = 0x4C
};

static uint32_t be32(const uint8_t* p) {
  return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}
static uint16_t be16(const uint8_t* p) { return (uint16_t)(p[0] << 8 | p[1]); }
// xex2_version: major:4 minor:4 build:16 qfe:8 of a big-endian u32
static const char* vstr(uint32_t v) {
  static char buf[6][24];
  static int n = 0;
  snprintf(buf[n & 7], 24, "%u.%u.%u.%u", (v >> 28) & 0xF, (v >> 24) & 0xF,
           (v >> 8) & 0xFFFF, v & 0xFF);
  return buf[n++ & 7];
}

static void aes_decrypt_buffer(const uint8_t* key, const uint8_t* in, size_t len,
                               uint8_t* out) {
  uint32_t rk[4 * (MAXNR + 1)];
  uint8_t ivec[16] = {0};
  int32_t Nr = rijndaelKeySetupDec(rk, key, 128);
  const uint8_t* ct = in;
  uint8_t* pt = out;
  for (size_t n = 0; n < len; n += 16, ct += 16, pt += 16) {
    uint8_t tmp[16];
    rijndaelDecrypt(rk, Nr, ct, tmp);
    for (int i = 0; i < 16; i++) {
      pt[i] = tmp[i] ^ ivec[i];
      ivec[i] = ct[i];
    }
  }
}

static void sha1_of(const uint8_t* data, size_t len, uint8_t out[20]) {
  sha1::SHA1 s;
  s.processBytes(data, len);
  s.finalize(out);
}

// ---- mspack memory system (from xenia lzx.cc) ----
typedef struct mspack_memory_file_t {
  mspack_system sys;
  void* buffer;
  off_t buffer_size;
  off_t offset;
} mspack_memory_file;

static mspack_memory_file* mspack_memory_open(mspack_system* sys, void* buffer,
                                              const size_t buffer_size) {
  auto memfile = (mspack_memory_file*)std::calloc(1, sizeof(mspack_memory_file));
  memfile->buffer = buffer;
  memfile->buffer_size = (off_t)buffer_size;
  memfile->offset = 0;
  return memfile;
}
static int mspack_memory_read(mspack_file* file, void* buffer, int chars) {
  auto memfile = (mspack_memory_file*)file;
  const off_t remaining = memfile->buffer_size - memfile->offset;
  const off_t total = std::min(static_cast<off_t>(chars), remaining);
  std::memcpy(buffer, (uint8_t*)memfile->buffer + memfile->offset, total);
  memfile->offset += total;
  return (int)total;
}
static int mspack_memory_write(mspack_file* file, void* buffer, int chars) {
  auto memfile = (mspack_memory_file*)file;
  const off_t remaining = memfile->buffer_size - memfile->offset;
  const off_t total = std::min(static_cast<off_t>(chars), remaining);
  std::memcpy((uint8_t*)memfile->buffer + memfile->offset, buffer, total);
  memfile->offset += total;
  return (int)total;
}
static void* mspack_memory_alloc(mspack_system* sys, size_t chars) {
  return std::calloc(chars, 1);
}
static void mspack_memory_free(void* ptr) { std::free(ptr); }
static void mspack_memory_copy(void* src, void* dest, size_t chars) {
  std::memcpy(dest, src, chars);
}
static mspack_system* mspack_memory_sys_create() {
  auto sys = (mspack_system*)std::calloc(1, sizeof(mspack_system));
  sys->read = mspack_memory_read;
  sys->write = mspack_memory_write;
  sys->alloc = mspack_memory_alloc;
  sys->free = mspack_memory_free;
  sys->copy = mspack_memory_copy;
  return sys;
}

static int bit_scan_forward(uint32_t v, uint32_t* idx) {
  if (!v) return 0;
  *idx = __builtin_ctz(v);
  return 1;
}

static int lzx_decompress(const void* lzx_data, size_t lzx_len, void* dest,
                          size_t dest_len, uint32_t window_size,
                          void* window_data, size_t window_data_len) {
  uint32_t window_bits;
  if (!bit_scan_forward(window_size, &window_bits)) return 1;

  mspack_system* sys = mspack_memory_sys_create();
  mspack_memory_file* lzxsrc = mspack_memory_open(sys, (void*)lzx_data, lzx_len);
  mspack_memory_file* lzxdst = mspack_memory_open(sys, dest, dest_len);
  lzxd_stream* lzxd = lzxd_init(sys, (mspack_file*)lzxsrc, (mspack_file*)lzxdst,
                                window_bits, 0, 0x8000, (off_t)dest_len, 0);
  int result_code = 1;
  if (lzxd) {
    if (window_data) {   // prime the window, as xenia does for a delta stream
      auto padding_len = window_size - window_data_len;
      std::memset(&lzxd->window[0], 0, padding_len);
      std::memcpy(&lzxd->window[padding_len], window_data, window_data_len);
      lzxd->ref_data_size = window_size;
    }
    result_code = lzxd_decompress(lzxd, (off_t)dest_len);
    lzxd_free(lzxd);
  }
  std::free(lzxsrc);
  std::free(lzxdst);
  std::free(sys);
  return result_code;
}

// xex2_delta_patch: old_addr, new_addr, uncompressed_len, compressed_len, data.
// A fill (len 0) and a copy (len 1) carry no data of their own.
static int lzxdelta_apply_patch(const uint8_t* patch, size_t patch_len,
                                uint32_t window_size, uint8_t* dest) {
  const uint8_t* p = patch;
  const uint8_t* end = patch + patch_len;
  while (end > p) {
    uint32_t old_addr = be32(p), new_addr = be32(p + 4);
    uint16_t ulen = be16(p + 8), clen = be16(p + 10);
    if (!old_addr && !new_addr && !ulen && !clen) break;   // terminator
    switch (clen) {
      case 0:
        std::memset(dest + new_addr, 0, ulen);
        break;
      case 1:
        std::memcpy(dest + new_addr, dest + old_addr, ulen);
        break;
      default: {
        int r = lzx_decompress(p + 12, clen, dest + new_addr, ulen, window_size,
                               dest + old_addr, ulen);
        if (r) {
          fprintf(stderr, "delta lzx error %d (old=%#x new=%#x ulen=%#x clen=%#x)\n",
                  r, old_addr, new_addr, ulen, clen);
          return r;
        }
        break;
      }
    }
    p += (clen > 1) ? 12 + clen : 12;
  }
  return 0;
}

struct Xex {
  std::vector<uint8_t> f;   // the file
  uint32_t hsize, sec_off, count, image_base;
  const uint8_t* sec;

  uint32_t opt(uint32_t key) const {
    for (uint32_t i = 0; i < count; i++)
      if (be32(&f[0x18 + i * 8]) == key) return be32(&f[0x18 + i * 8 + 4]);
    return 0xFFFFFFFFu;
  }
  void open(const char* path) {
    FILE* fp = fopen(path, "rb");
    if (!fp) { fprintf(stderr, "cannot open %s\n", path); exit(1); }
    fseek(fp, 0, SEEK_END);
    long n = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    f.resize(n);
    if (fread(f.data(), 1, n, fp) != (size_t)n) {
      fprintf(stderr, "short read on %s\n", path);
      exit(1);
    }
    fclose(fp);
    if (memcmp(f.data(), "XEX2", 4) != 0) {
      fprintf(stderr, "%s: not a XEX2\n", path);
      exit(2);
    }
    hsize = be32(&f[8]);
    sec_off = be32(&f[0x10]);
    count = be32(&f[0x14]);
    sec = f.data() + sec_off;
    image_base = opt(OPT_BASE_ADDRESS);
    if (opt(OPT_FILE_FORMAT_INFO) == 0xFFFFFFFFu) {
      fprintf(stderr, "%s: no FILE_FORMAT_INFO\n", path);
      exit(2);
    }
  }
  uint32_t ffi() const { return opt(OPT_FILE_FORMAT_INFO); }
  uint16_t encryption() const { return be16(&f[ffi() + 4]); }
  uint16_t compression() const { return be16(&f[ffi() + 6]); }
  uint32_t window() const { return be32(&f[ffi() + 8]); }
  uint32_t image_size() const { return be32(sec + 4); }
  uint32_t version_value() const {   // EXECUTION_INFO.version_value
    uint32_t o = opt(OPT_EXECUTION_INFO);
    return o == 0xFFFFFFFFu ? 0 : be32(&f[o + 4]);
  }
};

int main(int argc, char** argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: %s base.xex patch.xexp|<-> out_image.bin [out_header.bin]\n"
                    "  a patch of - stops after unpacking the base, writing the "
                    "un-updated image\n", argv[0]);
    return 2;
  }
  bool base_only = !strcmp(argv[2], "-");
  Xex base, xexp;
  base.open(argv[1]);
  if (!base_only) xexp.open(argv[2]);
  const char* out_image = argv[3];
  const char* out_header = argc > 4 ? argv[4] : nullptr;
  fprintf(stderr, "base: image %#x at %#x, version %s, %s + %s\n", base.image_size(),
          base.image_base, vstr(base.version_value()),
          base.encryption() ? "encrypted" : "plain",
          base.compression() == 2 ? "lzx" : base.compression() == 0 ? "plain" : "other");

  // ---- the base image: decrypt, then remove the lzx blocks and decompress ----
  uint8_t session[16];
  aes_decrypt_buffer(xe_xex2_retail_key, base.sec + 0x150, 16, session);
  size_t data_len = base.f.size() - base.hsize;
  std::vector<uint8_t> dec(data_len);
  if (base.encryption() == 1)
    aes_decrypt_buffer(session, base.f.data() + base.hsize, data_len, dec.data());
  else
    std::memcpy(dec.data(), base.f.data() + base.hsize, data_len);

  std::vector<uint8_t> image;
  if (base.compression() == 2) {
    // xex2_file_normal_compression_info: window size, then the first block's
    // {size, hash}; each block starts with the *next* block's size and hash,
    // then its own lzx segments as {u16 size, bytes}, ended by a 0 word.
    std::vector<uint8_t> concat;
    uint32_t ffi = base.ffi();
    uint32_t size = be32(&base.f[ffi + 0xC]);
    const uint8_t* hash = &base.f[ffi + 0x10];
    const uint8_t* p = dec.data();
    int nblocks = 0;
    while (size) {
      const uint8_t* start = p;
      uint8_t digest[20];
      sha1_of(p, size, digest);
      if (memcmp(digest, hash, 20) != 0) {
        fprintf(stderr, "base block hash mismatch (wrong key?)\n");
        return 2;
      }
      uint32_t next_size = be32(p);
      const uint8_t* next_hash = p + 4;
      p += 24;
      while (uint16_t cs = be16(p)) {
        p += 2;
        concat.insert(concat.end(), p, p + cs);
        p += cs;
      }
      p = start + size;              // the next block follows this one
      size = next_size;
      hash = next_hash;
      nblocks++;
    }
    fprintf(stderr, "%d base blocks verified, lzx stream %#zx -> image %#x (window %#x)\n",
            nblocks, concat.size(), base.image_size(), base.window());
    image.resize(base.image_size());
    int r = lzx_decompress(concat.data(), concat.size(), image.data(),
                           base.image_size(), base.window(), nullptr, 0);
    if (r) { fprintf(stderr, "lzx_decompress failed: %d\n", r); return 2; }
  } else if (base.compression() == 0) {
    image.assign(dec.begin(), dec.begin() + std::min<size_t>(dec.size(),
                                                             base.image_size()));
  } else {
    fprintf(stderr, "base compression %u unsupported\n", base.compression());
    return 2;
  }
  if (memcmp(image.data(), "MZ", 2) != 0) fprintf(stderr, "warning: no MZ header\n");

  if (base_only) {                                    // the un-updated image only
    FILE* out = fopen(out_image, "wb");
    if (!out) { fprintf(stderr, "cannot write %s\n", out_image); return 2; }
    fwrite(image.data(), 1, image.size(), out);
    fclose(out);
    fprintf(stderr, "%s: %#zx bytes (loaded at %#x), no update applied\n",
            out_image, image.size(), base.image_base);
    if (out_header) {
      out = fopen(out_header, "wb");
      fwrite(base.f.data(), 1, base.hsize, out);
      fclose(out);
    }
    return 0;
  }

  // ---- the .xexp: descriptor, header delta, image delta ----
  uint32_t desc = xexp.opt(OPT_DELTA_PATCH_DESCRIPTOR);
  if (desc == 0xFFFFFFFFu) { fprintf(stderr, "xexp: no delta patch descriptor\n"); return 2; }
  uint32_t xffi = xexp.ffi();
  if (xexp.compression() != 3) {
    fprintf(stderr, "xexp: compression %u is not DELTA\n", xexp.compression());
    return 2;
  }
  uint32_t target_version = be32(&xexp.f[desc + DESC_TARGET_VERSION]);
  uint32_t source_version = be32(&xexp.f[desc + DESC_SOURCE_VERSION]);
  fprintf(stderr, "update: %s -> %s\n", vstr(source_version), vstr(target_version));

  uint8_t digest[20];
  sha1_of(base.sec + 8, 0x100, digest);
  if (memcmp(digest, &xexp.f[desc + DESC_DIGEST_SOURCE], 20) != 0) {
    fprintf(stderr, "error: the update was not made for this base xex "
                    "(its signature digest differs)\n");
    return 2;
  }
  fprintf(stderr, "the update is for this base xex (signature digest matches)\n");
  if (source_version != base.version_value())
    fprintf(stderr, "warning: the update wants base %s, this xex is %s\n",
            vstr(source_version), vstr(base.version_value()));

  // the header delta: the inline xex2_delta_patch at the end of the descriptor
  std::vector<uint8_t> hdr(base.f.begin(), base.f.begin() + base.hsize);
  const uint8_t* hdr_info = &xexp.f[desc + DESC_INFO];
  uint32_t hdr_target_size = be32(&xexp.f[desc + DESC_TARGET_HEADERS]);
  uint32_t hdr_src_off = be32(&xexp.f[desc + DESC_HEADERS_SOURCE_OFFSET]);
  uint32_t hdr_src_size = be32(&xexp.f[desc + DESC_HEADERS_SOURCE_SIZE]);
  uint32_t hdr_tgt_off = be32(&xexp.f[desc + DESC_HEADERS_TARGET_OFFSET]);
  if (hdr_target_size > hdr.size()) hdr.resize(hdr_target_size);
  if (hdr_src_off && hdr_src_size) {
    if (hdr_src_off + hdr_src_size > hdr.size() || hdr_tgt_off + hdr_src_size > hdr.size()) {
      fprintf(stderr, "header delta source/target outside the header\n");
      return 2;
    }
    std::memmove(hdr.data() + hdr_tgt_off, hdr.data() + hdr_src_off, hdr_src_size);
  }
  int r = lzxdelta_apply_patch(hdr_info, (size_t)be16(hdr_info + 10) + 12,
                               base.window(), hdr.data());
  if (r) { fprintf(stderr, "header delta failed: %d\n", r); return 2; }
  uint32_t new_image_size = be32(&hdr[be32(&hdr[0x10]) + 4]);
  fprintf(stderr, "header patched: image %#x -> %#x\n", base.image_size(), new_image_size);

  // the image delta: the .xexp's data area, with the .xexp's own session key,
  // which is the *updated* security info's aes key (decrypted with the retail key)
  uint8_t new_session[16], xsession[16], delta_key[16];
  uint32_t new_sec_off = be32(&hdr[0x10]);
  aes_decrypt_buffer(xe_xex2_retail_key, &hdr[new_sec_off + 0x150], 16, new_session);
  aes_decrypt_buffer(new_session, xexp.f.data() + xexp.sec_off + 0x150, 16, xsession);
  aes_decrypt_buffer(new_session, &xexp.f[desc + DESC_IMAGE_KEY_SOURCE], 16, delta_key);
  if (memcmp(delta_key, session, 16) != 0)
    fprintf(stderr, "warning: the image key is not the base session key\n");
  else
    fprintf(stderr, "delta image key OK\n");
  size_t xdata_len = xexp.f.size() - xexp.hsize;
  std::vector<uint8_t> xdec(xdata_len);
  aes_decrypt_buffer(xsession, xexp.f.data() + xexp.hsize, xdata_len, xdec.data());

  uint32_t img_src_off = be32(&xexp.f[desc + DESC_IMAGE_SOURCE_OFFSET]);
  uint32_t img_src_size = be32(&xexp.f[desc + DESC_IMAGE_SOURCE_SIZE]);
  uint32_t img_tgt_off = be32(&xexp.f[desc + DESC_IMAGE_TARGET_OFFSET]);
  if (image.size() < new_image_size) image.resize(new_image_size);
  if (img_src_off && img_src_size) {
    if (img_src_off + img_src_size > image.size() ||
        img_tgt_off + img_src_size > image.size()) {
      fprintf(stderr, "image delta source/target outside the image\n");
      return 2;
    }
    std::memmove(image.data() + img_tgt_off, image.data() + img_src_off, img_src_size);
  }
  if (img_tgt_off + img_src_size < new_image_size)
    std::memset(image.data() + img_tgt_off + img_src_size, 0,
                new_image_size - (img_tgt_off + img_src_size));

  // the same block chain as the base's, but each block holds delta entries
  const uint8_t* p = xdec.data();
  const uint8_t* dec_end = xdec.data() + xdec.size();
  uint32_t block_size = be32(&xexp.f[xffi + 0xC]);
  const uint8_t* block_hash = &xexp.f[xffi + 0x10];
  int nblocks = 0;
  while (block_size) {
    if (p + block_size > dec_end) {
      fprintf(stderr, "update block %d runs past the end of the file\n", nblocks + 1);
      return 2;
    }
    uint8_t calc[20];
    sha1_of(p, block_size, calc);
    if (memcmp(calc, block_hash, 20) != 0) {
      fprintf(stderr, "update block %d hash mismatch (wrong key?)\n", nblocks + 1);
      return 2;
    }
    uint32_t next_size = be32(p);
    const uint8_t* next_hash = p + 4;
    r = lzxdelta_apply_patch(p + 24, block_size - 24, xexp.window(), image.data());
    if (r) { fprintf(stderr, "image delta block %d failed: %d\n", nblocks + 1, r); return 2; }
    p += block_size;
    block_size = next_size;
    block_hash = next_hash;
    nblocks++;
  }
  fprintf(stderr, "%d image delta blocks applied\n", nblocks);

  FILE* out = fopen(out_image, "wb");
  if (!out) { fprintf(stderr, "cannot write %s\n", out_image); return 2; }
  fwrite(image.data(), 1, image.size(), out);
  fclose(out);
  fprintf(stderr, "%s: %#zx bytes (loaded at %#x)\n", out_image, image.size(),
          base.image_base);
  if (out_header) {
    out = fopen(out_header, "wb");
    if (!out) { fprintf(stderr, "cannot write %s\n", out_header); return 2; }
    fwrite(hdr.data(), 1, hdr.size(), out);
    fclose(out);
    fprintf(stderr, "%s: %#zx bytes\n", out_header, hdr.size());
  }
  return 0;
}
