package com.jsh.aidesk.serverapi.common.response;

import com.jsh.aidesk.serverapi.common.util.DateUtil;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class ResponseJson<T> {

    private int result;
    private String message;
    private T data;

    public ResponseJson() {
        this.result = 800;
        this.message = "Response Undefined";
    }

    public ResponseJson(CodeData codeData, T data) {
        this.result = codeData.getCode();
        this.message = codeData.getMessage();
        this.data = data;
    }

    public String getTimestamp() {
        return DateUtil.printCurrentTime();
    }

    public static <T> ResponseJson<T> ok(T data) {
        return new ResponseJson<>(ResponseCode.SUCCESS, data);
    }

    public static <T> ResponseJson<T> ok(CodeData codeData) {
        return new ResponseJson<>(codeData, null);
    }

    public static <T> ResponseJson<T> ok(CodeData codeData, T data) {
        return new ResponseJson<>(codeData, data);
    }

    public static <T> ResponseJson<T> fail(CodeData codeData) {
        return new ResponseJson<>(codeData, null);
    }

    public static <T> ResponseJson<T> fail(CodeData codeData, T data) {
        return new ResponseJson<>(codeData, data);
    }

    public static <T> ResponseJson<T> fail(int code, String message) {
        return new ResponseJson<>(new CodeData() {
            @Override public int getCode() { return code; }
            @Override public String getMessage() { return message; }
        }, null);
    }
}
