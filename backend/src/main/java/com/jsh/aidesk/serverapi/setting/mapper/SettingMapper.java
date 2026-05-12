package com.jsh.aidesk.serverapi.setting.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface SettingMapper {

    String selectValue(@Param("key") String key);

    int upsertValue(@Param("key") String key, @Param("value") String value);
}
