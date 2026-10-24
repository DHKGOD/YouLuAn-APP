package tw.edu.fju.trafficsafety.guardian;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 守護模式的判斷邏輯（純 Java，不依賴 Android，方便單元測試）。
 *
 * 規則：
 * 1. 依交通方式決定提醒距離：步行 60 m、騎車 120 m、開車 220 m；「自動」依速度判斷。
 * 2. 搭乘大眾運輸（transit）時不提醒（乘客不需要路口提醒）。
 * 3. 只在「正在接近」路口時提醒：距離比上一次定位更近，或剛進入範圍。
 * 4. 同一個路口 10 分鐘內不重複提醒。
 */
public class GuardianEngine {

    public static class Hotspot {
        public final int id;
        public final String name;
        public final double lat, lon;
        public final String level;
        public final int accidents;

        public Hotspot(int id, String name, double lat, double lon, String level, int accidents) {
            this.id = id;
            this.name = name;
            this.lat = lat;
            this.lon = lon;
            this.level = level;
            this.accidents = accidents;
        }
    }

    public static class Alert {
        public final Hotspot hotspot;
        public final double distance;
        public final String mode;

        Alert(Hotspot hotspot, double distance, String mode) {
            this.hotspot = hotspot;
            this.distance = distance;
            this.mode = mode;
        }
    }

    public static final long COOLDOWN_MS = 10 * 60 * 1000L;

    private final List<Hotspot> hotspots = new ArrayList<>();
    private final Map<Integer, Double> lastDistance = new HashMap<>();
    private final Map<Integer, Long> lastAlertAt = new HashMap<>();
    private String userMode = "auto"; // auto / foot / bike / car / transit
    private double radiusScale = 1.0; // 長輩模式 1.3：提早提醒

    public synchronized void setHotspots(List<Hotspot> list) {
        hotspots.clear();
        hotspots.addAll(list);
        lastDistance.keySet().retainAll(idsOf(list));
    }

    public synchronized int size() {
        return hotspots.size();
    }

    public synchronized void setUserMode(String mode) {
        userMode = mode == null ? "auto" : mode;
    }

    public synchronized String getUserMode() {
        return userMode;
    }

    public synchronized void setRadiusScale(double scale) {
        radiusScale = scale > 0 ? scale : 1.0;
    }

    /** 依使用者設定與速度（m/s，未知時 <0）決定實際交通方式。 */
    public String effectiveMode(double speed) {
        if (!"auto".equals(userMode)) return userMode;
        if (speed < 0) return "foot";
        if (speed < 2.5) return "foot";     // 約 9 km/h 以下
        if (speed < 8.0) return "bike";     // 約 29 km/h 以下
        return "car";
    }

    public static double alertRadius(String mode) {
        switch (mode) {
            case "car": return 220;
            case "bike": return 120;
            default: return 60;
        }
    }

    /** 每次定位呼叫一次；回傳要提醒的路口（沒有則回傳 null）。 */
    public synchronized Alert onLocation(double lat, double lon, double speed, long now) {
        String mode = effectiveMode(speed);
        if ("transit".equals(mode)) return null;
        double radius = alertRadius(mode) * radiusScale;
        Alert best = null;
        for (Hotspot hotspot : hotspots) {
            double distanceM = distance(lat, lon, hotspot.lat, hotspot.lon);
            Double previousDistance = lastDistance.put(hotspot.id, distanceM);
            if (distanceM > radius) continue;

            // 新進入範圍，或比上次靠近超過 0.5 公尺，才算接近路口。
            boolean approaching = previousDistance == null || previousDistance > radius
                    || distanceM < previousDistance - 0.5;
            Long lastAlertTime = lastAlertAt.get(hotspot.id);
            boolean cooldownFinished = lastAlertTime == null || now - lastAlertTime > COOLDOWN_MS;
            boolean nearerThanCurrent = best == null || distanceM < best.distance;
            if (approaching && cooldownFinished && nearerThanCurrent) {
                best = new Alert(hotspot, distanceM, mode);
            }
        }
        if (best != null) lastAlertAt.put(best.hotspot.id, now);
        return best;
    }

    /** 標記為已提醒（App 內模擬行走交給背景服務時，已提醒過的路口不再重複）。 */
    public synchronized void markAlerted(int id, long now) {
        lastAlertAt.put(id, now);
    }

    /** 最近的危險路口（狀態列顯示用）。 */
    public synchronized Object[] nearest(double lat, double lon) {
        Hotspot best = null;
        double nearestDistance = Double.MAX_VALUE;
        for (Hotspot hotspot : hotspots) {
            double distanceM = distance(lat, lon, hotspot.lat, hotspot.lon);
            if (distanceM < nearestDistance) {
                nearestDistance = distanceM;
                best = hotspot;
            }
        }
        return best == null ? null : new Object[]{best, nearestDistance};
    }

    public static double distance(double lat1, double lon1, double lat2, double lon2) {
        double r = 6371000, p1 = Math.toRadians(lat1), p2 = Math.toRadians(lat2);
        double dp = p2 - p1, dl = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dp / 2) * Math.sin(dp / 2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2);
        return 2 * r * Math.asin(Math.sqrt(a));
    }

    private static java.util.Set<Integer> idsOf(List<Hotspot> list) {
        java.util.Set<Integer> ids = new java.util.HashSet<>();
        for (Hotspot hotspot : list) ids.add(hotspot.id);
        return ids;
    }
}
