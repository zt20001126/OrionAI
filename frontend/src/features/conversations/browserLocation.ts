import type { UserLocationContext } from "./conversationApi";

const LOCATION_REQUEST_TIMEOUT_MS = 10_000;
const LOCATION_CACHE_MAX_AGE_MS = 60_000;

/** 获取浏览器定位；输入：无；输出：经纬度或明确失败状态；调用方：数字人授权题卡提交。 */
export function requestBrowserLocation(): Promise<UserLocationContext> {
  if (!navigator.geolocation) return Promise.resolve({ status: "unavailable" });

  return new Promise((resolve) => {
    try {
      navigator.geolocation.getCurrentPosition(
        ({ coords }) =>
          resolve({
            status: "granted",
            latitude: coords.latitude,
            longitude: coords.longitude,
            accuracy_meters: coords.accuracy,
          }),
        (error) =>
          resolve({ status: error.code === error.PERMISSION_DENIED ? "denied" : "unavailable" }),
        {
          enableHighAccuracy: true,
          timeout: LOCATION_REQUEST_TIMEOUT_MS,
          maximumAge: LOCATION_CACHE_MAX_AGE_MS,
        },
      );
    } catch {
      resolve({ status: "unavailable" });
    }
  });
}

