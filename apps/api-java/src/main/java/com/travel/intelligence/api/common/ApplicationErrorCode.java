package com.travel.intelligence.api.common;

import org.springframework.http.HttpStatus;

public enum ApplicationErrorCode {
    AGENT_ERROR("agent_error", HttpStatus.BAD_GATEWAY),
    AGENT_TIMEOUT("agent_timeout", HttpStatus.GATEWAY_TIMEOUT),
    AGENT_UNAVAILABLE("agent_unavailable", HttpStatus.BAD_GATEWAY),
    BAD_CREDENTIALS("bad_credentials", HttpStatus.UNAUTHORIZED),
    CONVERSATION_NOT_FOUND("conversation_not_found", HttpStatus.NOT_FOUND),
    EMAIL_EXISTS("email_exists", HttpStatus.CONFLICT),
    RECORD_CORRUPT("record_corrupt", HttpStatus.INTERNAL_SERVER_ERROR),
    RECORD_NOT_FOUND("record_not_found", HttpStatus.NOT_FOUND),
    RECORD_WRITE_FAILED("record_write_failed", HttpStatus.INTERNAL_SERVER_ERROR),
    UNAUTHORIZED("unauthorized", HttpStatus.UNAUTHORIZED),
    USER_NOT_FOUND("user_not_found", HttpStatus.UNAUTHORIZED),
    USERNAME_EXISTS("username_exists", HttpStatus.CONFLICT);

    private final String code;
    private final HttpStatus httpStatus;

    ApplicationErrorCode(String code, HttpStatus httpStatus) {
        this.code = code;
        this.httpStatus = httpStatus;
    }

    public String code() {
        return code;
    }

    public HttpStatus httpStatus() {
        return httpStatus;
    }
}
