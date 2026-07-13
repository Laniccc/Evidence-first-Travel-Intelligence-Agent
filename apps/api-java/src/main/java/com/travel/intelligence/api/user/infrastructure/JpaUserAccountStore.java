package com.travel.intelligence.api.user.infrastructure;

import com.travel.intelligence.api.user.application.UserAccountStore;
import com.travel.intelligence.api.user.domain.UserAccount;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class JpaUserAccountStore implements UserAccountStore {

    private final UserAccountRepository repository;

    public JpaUserAccountStore(UserAccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<UserAccount> findById(Long id) {
        return repository.findById(id).map(UserAccountMapper::toDomain);
    }

    @Override
    public Optional<UserAccount> findByUsername(String username) {
        return repository.findByUsername(username).map(UserAccountMapper::toDomain);
    }

    @Override
    public Optional<UserAccount> findByEmail(String email) {
        return repository.findByEmail(email).map(UserAccountMapper::toDomain);
    }

    @Override
    public boolean existsByUsername(String username) {
        return repository.existsByUsername(username);
    }

    @Override
    public boolean existsByEmail(String email) {
        return repository.existsByEmail(email);
    }

    @Override
    public UserAccount save(UserAccount account) {
        return UserAccountMapper.toDomain(repository.save(UserAccountMapper.toEntity(account)));
    }
}
