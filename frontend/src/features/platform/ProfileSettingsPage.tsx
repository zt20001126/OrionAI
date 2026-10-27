import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { PlatformIcon } from "./PlatformIcon";
import { getUserProfile, updateUserProfile, type UserProfile } from "./profileApi";

const MAX_NICKNAME_LENGTH = 20;
const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const ACCEPTED_AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

/** 个人资料设置页面，允许当前用户编辑昵称和头像并查看账号时间信息。 */
export function ProfileSettingsPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [nickname, setNickname] = useState("");
  const [selectedAvatar, setSelectedAvatar] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadRevision, setLoadRevision] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const avatarButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let isActive = true;
    getUserProfile()
      .then((loadedProfile) => {
        if (!isActive) return;
        setProfile(loadedProfile);
        setNickname(loadedProfile.nickname);
        setSelectedAvatar(null);
      })
      .catch(() => {
        if (isActive) setLoadError("暂时无法读取个人资料，请检查连接后重试。");
      })
      .finally(() => {
        if (isActive) setIsLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, [loadRevision]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const nicknameCharacterCount = Array.from(nickname).length;
  const hasUnsavedChanges =
    profile !== null && (nickname !== profile.nickname || selectedAvatar !== null);
  const isNicknameValid =
    nickname.trim().length > 0 && Array.from(nickname.trim()).length <= MAX_NICKNAME_LENGTH;

  function handleAvatarSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0] ?? null;
    event.currentTarget.value = "";
    avatarButtonRef.current?.focus();
    if (!file) return;

    setSaveError(null);
    setSuccessMessage(null);
    if (!ACCEPTED_AVATAR_TYPES.has(file.type)) {
      setSaveError("头像仅支持 PNG、JPEG 或 WebP 图片。");
      return;
    }
    if (file.size === 0 || file.size > MAX_AVATAR_BYTES) {
      setSaveError("头像文件不能为空，且大小不能超过 5 MiB。");
      return;
    }
    setSelectedAvatar(file);
    setPreviewUrl(URL.createObjectURL(file));
  }

  function cancelChanges() {
    if (!profile) return;
    setNickname(profile.nickname);
    setSelectedAvatar(null);
    setPreviewUrl(null);
    setSaveError(null);
    setSuccessMessage(null);
  }

  async function saveChanges() {
    if (!profile || !isNicknameValid || !hasUnsavedChanges) return;

    setIsSaving(true);
    setSaveError(null);
    setSuccessMessage(null);
    try {
      const updatedProfile = await updateUserProfile(nickname.trim(), selectedAvatar);
      setProfile(updatedProfile);
      setNickname(updatedProfile.nickname);
      setSelectedAvatar(null);
      setPreviewUrl(null);
      setSuccessMessage("个人资料已保存。");
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "保存失败，请稍后重试。");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <section aria-live="polite" className="profile-settings-state" role="status">
        <span className="status-spinner" aria-hidden="true" />
        <p>正在加载个人资料…</p>
      </section>
    );
  }

  if (!profile) {
    return (
      <section aria-labelledby="profile-settings-title" className="profile-settings-state">
        <h1 id="profile-settings-title">个人设置</h1>
        <p className="profile-settings__message profile-settings__message--error" role="alert">
          {loadError}
        </p>
        <button
          className="button button--outline"
          onClick={() => {
            setLoadError(null);
            setIsLoading(true);
            setLoadRevision((revision) => revision + 1);
          }}
          type="button"
        >
          重试
        </button>
      </section>
    );
  }

  const avatarSource = previewUrl ?? profile.avatar_url;

  return (
    <section aria-labelledby="profile-settings-title" className="profile-settings-page">
      <div className="profile-settings">
        <header className="profile-settings__header">
          <h1 id="profile-settings-title">个人设置</h1>
        </header>

        <div className="profile-settings__avatar-section">
          <div className="profile-settings__avatar-wrap">
            <img
              alt={`${nickname || profile.account} 的头像`}
              className="profile-settings__avatar"
              src={avatarSource}
            />
            <button
              aria-label="更换头像"
              className="profile-settings__avatar-button"
              disabled={isSaving}
              onClick={() => fileInputRef.current?.click()}
              ref={avatarButtonRef}
              type="button"
            >
              <PlatformIcon name="camera" size={19} />
            </button>
            <input
              accept="image/jpeg,image/png,image/webp"
              aria-label="选择头像文件"
              className="profile-settings__file-input"
              onChange={handleAvatarSelection}
              ref={fileInputRef}
              tabIndex={-1}
              type="file"
            />
          </div>
        </div>

        <div className="profile-settings__field">
          <label htmlFor="profile-nickname">用户昵称</label>
          <div className="profile-settings__input-wrap">
            <input
              autoComplete="nickname"
              className="form-input"
              disabled={isSaving}
              id="profile-nickname"
              maxLength={MAX_NICKNAME_LENGTH}
              onChange={(event) => {
                setNickname(event.currentTarget.value);
                setSaveError(null);
                setSuccessMessage(null);
              }}
              value={nickname}
            />
            <span aria-live="polite" className="profile-settings__character-count">
              {nicknameCharacterCount}/{MAX_NICKNAME_LENGTH}
            </span>
          </div>
        </div>

        <dl className="profile-settings__details">
          <div className="profile-settings__detail-row">
            <dt>
              <PlatformIcon name="user" size={20} />
              <span>账号</span>
            </dt>
            <dd>{profile.account}</dd>
          </div>
          <div className="profile-settings__detail-row">
            <dt>
              <PlatformIcon name="calendar" size={20} />
              <span>创建时间</span>
            </dt>
            <dd>{formatDateTime(profile.created_at)}</dd>
          </div>
          <div className="profile-settings__detail-row">
            <dt>
              <PlatformIcon name="clock" size={20} />
              <span>最后登录时间</span>
            </dt>
            <dd>{formatDateTime(profile.last_login_at)}</dd>
          </div>
        </dl>

        <div aria-live="polite" className="profile-settings__feedback">
          {saveError && (
            <p className="profile-settings__message profile-settings__message--error" role="alert">
              {saveError}
            </p>
          )}
          {successMessage && (
            <p className="profile-settings__message profile-settings__message--success" role="status">
              {successMessage}
            </p>
          )}
        </div>

        <footer className="profile-settings__actions">
          <button
            className="button button--outline"
            disabled={!hasUnsavedChanges || isSaving}
            onClick={cancelChanges}
            type="button"
          >
            取消
          </button>
          <button
            className="button button--primary"
            disabled={!hasUnsavedChanges || !isNicknameValid || isSaving}
            onClick={() => void saveChanges()}
            type="button"
          >
            {isSaving ? "正在保存…" : "保存"}
          </button>
        </footer>
      </div>
    </section>
  );
}

function formatDateTime(value: string | null): string {
  if (!value) return "暂无记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
