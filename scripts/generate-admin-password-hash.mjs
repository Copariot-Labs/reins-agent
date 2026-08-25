import {
  randomBytes,
  scryptSync,
} from 'node:crypto'

const MIN_PASSWORD_LENGTH = 12
const MAX_PASSWORD_LENGTH = 256
const KEY_LENGTH = 64

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = []

    process.stdin.setEncoding('utf8')
    process.stdin.on('data', chunk => chunks.push(chunk))
    process.stdin.on('end', () => resolve(chunks.join('')))
    process.stdin.on('error', reject)
  })
}

function stripPipelineNewline(value) {
  return value.endsWith('\r\n')
    ? value.slice(0, -2)
    : value.endsWith('\n')
      ? value.slice(0, -1)
      : value
}

function validEncodedHash(value) {
  const parts = value.trim().split('$')

  if (
    parts.length !== 3 ||
    parts[0] !== 'scrypt' ||
    !/^[A-Za-z0-9_-]+$/.test(parts[1]) ||
    !/^[A-Za-z0-9_-]+$/.test(parts[2])
  ) {
    return false
  }

  return (
    Buffer.from(parts[1], 'base64url').length >= 16 &&
    Buffer.from(parts[2], 'base64url').length === KEY_LENGTH
  )
}

const input = await readStdin()

if (process.argv.includes('--validate')) {
  if (!validEncodedHash(input)) {
    console.error('Administrator password hash must use the Reins scrypt format.')
    process.exit(1)
  }

  process.stdout.write('valid\n')
  process.exit(0)
}

const password = stripPipelineNewline(input)
const length = Array.from(password).length

if (length < MIN_PASSWORD_LENGTH || length > MAX_PASSWORD_LENGTH) {
  console.error(
    `Administrator password must contain ${MIN_PASSWORD_LENGTH}-${MAX_PASSWORD_LENGTH} characters.`,
  )
  process.exit(1)
}

const salt = randomBytes(16)
const hash = scryptSync(password, salt, KEY_LENGTH)

process.stdout.write(
  `scrypt$${salt.toString('base64url')}$${hash.toString('base64url')}\n`,
)
