// Dependency-free PWA icon generator: writes solid-background PNGs with three
// "juggling ball" dots, at 192 and 512 px, into public/. Uses only Node built-ins
// (zlib for IDAT compression, manual CRC32 for chunk checksums).
//
//   node scripts/gen-icons.mjs

import { deflateSync } from 'node:zlib'
import { writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public')
mkdirSync(OUT, { recursive: true })

// Brand palette (matches quasar.variables.scss).
const BG = [59, 111, 224] // #3B6FE0 friendly blue
const BALLS = [
  [255, 255, 255], // white
  [255, 138, 101], // coral accent
  [255, 209, 102], // amber
]

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c >>> 0
  }
  return t
})()
function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}
function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length, 0)
  const typeBuf = Buffer.from(type, 'ascii')
  const crcBuf = Buffer.alloc(4)
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0)
  return Buffer.concat([len, typeBuf, data, crcBuf])
}

function renderPng(size) {
  const cx = size / 2
  const cy = size / 2
  // Three balls arranged in a triangle within the maskable "safe zone".
  const r = size * 0.13
  const spread = size * 0.2
  const centers = [
    [cx, cy - spread],
    [cx - spread, cy + spread * 0.7],
    [cx + spread, cy + spread * 0.7],
  ]

  const raw = Buffer.alloc((size * 4 + 1) * size)
  let p = 0
  for (let y = 0; y < size; y++) {
    raw[p++] = 0 // filter: none
    for (let x = 0; x < size; x++) {
      let color = BG
      for (let i = 0; i < centers.length; i++) {
        const dx = x - centers[i][0]
        const dy = y - centers[i][1]
        if (dx * dx + dy * dy <= r * r) {
          color = BALLS[i]
          break
        }
      }
      raw[p++] = color[0]
      raw[p++] = color[1]
      raw[p++] = color[2]
      raw[p++] = 255
    }
  }

  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // color type: truecolor + alpha
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

for (const size of [192, 512]) {
  writeFileSync(join(OUT, `icon-${size}.png`), renderPng(size))
  console.log(`wrote public/icon-${size}.png`)
}
