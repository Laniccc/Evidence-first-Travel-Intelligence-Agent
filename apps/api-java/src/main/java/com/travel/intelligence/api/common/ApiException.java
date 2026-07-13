package com.travel.intelligence.api.common;

public class ApiException extends RuntimeException {

    private final ApplicationErrorCode errorCode;

    public ApiException(ApplicationErrorCode errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    public ApplicationErrorCode errorCode() {
        return errorCode;
    }

    public String code() {
        return errorCode.code();
    }
}
