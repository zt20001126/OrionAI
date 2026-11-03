import type { RefObject } from "react";

import { useAudioMouthLevel } from "../hooks/useAudioMouthLevel";
import type { DigitalHumanStatus } from "../types";
import { DigitalHumanAvatar3D } from "./DigitalHumanAvatar3D";

interface DigitalHumanAvatarHostProps {
  audioRef: RefObject<HTMLAudioElement | null>;
  isSpeaking: boolean;
  onLoadError: (error: Error) => void;
  status: DigitalHumanStatus;
}

/** Connects playback analysis to the renderer without making the chat page update per audio sample. */
export function DigitalHumanAvatarHost({
  audioRef,
  isSpeaking,
  onLoadError,
  status,
}: DigitalHumanAvatarHostProps) {
  const mouthOpen = useAudioMouthLevel(audioRef, isSpeaking);

  return <DigitalHumanAvatar3D mouthOpen={mouthOpen} onLoadError={onLoadError} status={status} />;
}
