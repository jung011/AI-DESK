package com.jsh.aidesk.serverapi.common.util;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public final class DateUtil {

    private static final ZoneId KST = ZoneId.of("Asia/Seoul");
    private static final DateTimeFormatter ISO_OFFSET =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSXXX");

    private DateUtil() {
    }

    public static String printCurrentTime() {
        return ZonedDateTime.now(KST).format(ISO_OFFSET);
    }

    public static String getCurrentDateTime(String pattern) {
        return ZonedDateTime.now(KST).format(DateTimeFormatter.ofPattern(pattern));
    }
}
