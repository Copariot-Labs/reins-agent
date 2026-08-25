import { resolve } from 'path'
import { config } from '../../config'
import { isPathWithin } from './hermes-path'

export function getProfileUploadDir(profile: string): string {
  void profile
  return resolve(config.uploadDir)
}

export function isInProfileUploadDir(filePath: string, profile: string): boolean {
  return isPathWithin(filePath, getProfileUploadDir(profile))
}
