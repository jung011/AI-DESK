package com.jsh.aidesk.serverapi.setting.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 사용자별 t_aidesk_setting 접근. PK 는 (account_sn, setting_key) — 모든 호출이 account_sn 동반.
 */
@Mapper
public interface SettingMapper {

    String selectValue(@Param("accountSn") Long accountSn, @Param("key") String key);

    int upsertValue(@Param("accountSn") Long accountSn, @Param("key") String key, @Param("value") String value);
}
